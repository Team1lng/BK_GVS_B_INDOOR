/*********************************************************************************
 *Copyright(C),2015-2020,
 *TUYA
 *FileName: tuya_ipc_dp_.c
 *
 * File Description：
 * 1. API implementation of DP point
 *
 * This file code is the basic code, users don't care it
 * Please do not modify any contents of this file at will.
 * Please contact the Product Manager if you need to modify it.
 *
 **********************************************************************************/
#include "utilities/uni_log.h"
#include "tuya_iot_config.h"
#include "tuya_ipc_api.h"
#include "tuya_cloud_com_defs.h"
#include "tuya_iot_config.h"
#include "ty_dp_define.h"
#include "ty_sdk_common.h"
#include "utilities/uni_log.h"
#include <stdio.h>
#include <string.h>
#include <pthread.h>
#include <stdlib.h>
#include <unistd.h>
#include <time.h>

#define TUYA_UNPACK_ENABLE 0
#if defined(TUYA_UNPACK_ENABLE) && (TUYA_UNPACK_ENABLE == 1)
#include "tuya_unpack.h"

ota_stream *ota_obj = NULL;
#endif

/* Only one download owns the shared staging file. Keep its write failure
 * sticky: a successful network result cannot make a partial file installable. */
typedef struct
{
    FILE *file;
    UINT_T expected;
    UINT_T received;
    BOOL_T failed;
    BOOL_T active;
    BOOL_T starting;
} GVS_OTA_DOWNLOAD;

static GVS_OTA_DOWNLOAD ota_download;
static pthread_mutex_t ota_download_mutex = PTHREAD_MUTEX_INITIALIZER;

OPERATE_RET __IPC_APP_upgrade_notify_cb(IN CONST FW_UG_S *fw, IN CONST INT_T download_result, IN PVOID_T pri_data)
{
    GVS_OTA_DOWNLOAD *download = (GVS_OTA_DOWNLOAD *)pri_data;
    OPERATE_RET result = OPRT_COM_ERROR;
    pthread_mutex_lock(&ota_download_mutex);
    if (download != &ota_download || !download->active)
    {
        pthread_mutex_unlock(&ota_download_mutex);
        return result;
    }

    if (download->file != NULL)
    {
        if (fclose(download->file) != 0)
        {
            download->failed = TRUE;
        }
        download->file = NULL;
    }
    else
    {
        download->failed = TRUE;
    }

    if (fw == NULL || download_result != OPRT_OK || download->failed ||
        download->received != download->expected)
    {
        unlink("/tmp/TWO_WIRE_APP");
    }
    else if (fw->tp == DEV_NM_ATH_SNGL)
    {
        /* Verify extraction before stopping the app or its watchdog. */
        if (system("tar -zxvf /tmp/TWO_WIRE_APP -C /tmp") == 0)
        {
            /* A wired device may have no Wi-Fi configuration to preserve. */
            system("cp /etc/config/wpa_supplicant.conf /app/data");
            extern int ak_drv_wdt_close(void);
            ak_drv_wdt_close();
            char version_name[64] = {0};
            char command[256];
            const char *name = strstr(fw->fw_url, "SAT_ANYKAOS_");
            size_t length = 0;
            if (name != NULL)
            {
                while (length < sizeof(version_name) - 1 &&
                       (name[length] == '_' || (name[length] >= '0' && name[length] <= '9') ||
                        (name[length] >= 'A' && name[length] <= 'Z')))
                {
                    version_name[length] = name[length];
                    ++length;
                }
            }
            if (length == 0) snprintf(version_name, sizeof(version_name), "SAT_ANYKAOS_UNKNOWN");
            snprintf(command, sizeof(command),
                     "killall daemon.sh;killall app.sh;killall ANYKA37E.BIN;/tmp/update.sh %s &", version_name);
            result = system(command) == 0 ? OPRT_OK : OPRT_COM_ERROR;
        }
    }
    else if (rename("/tmp/TWO_WIRE_APP", "/tmp/cbin.update") == 0)
    {
        extern bool tuya_ota_upgrade_event(void);
        result = tuya_ota_upgrade_event() ? OPRT_OK : OPRT_COM_ERROR;
    }

    download->active = FALSE;
    pthread_mutex_unlock(&ota_download_mutex);
    return result;
}

OPERATE_RET __IPC_APP_get_file_data_cb(IN CONST FW_UG_S *fw, IN CONST UINT_T total_len, IN CONST UINT_T offset,
                                      IN CONST BYTE_T *data, IN CONST UINT_T len, OUT UINT_T *remain_len, IN PVOID_T pri_data)
{
    GVS_OTA_DOWNLOAD *download = (GVS_OTA_DOWNLOAD *)pri_data;
    if (remain_len != NULL)
    {
        *remain_len = 0;
    }
    pthread_mutex_lock(&ota_download_mutex);
    if (download != &ota_download || !download->active)
    {
        pthread_mutex_unlock(&ota_download_mutex);
        return OPRT_COM_ERROR;
    }
    if (fw == NULL || data == NULL || len == 0 || download->file == NULL ||
        download->failed || total_len != download->expected || offset != download->received ||
        len > download->expected - download->received ||
        fwrite(data, 1, len, download->file) != len || fflush(download->file) != 0)
    {
        download->failed = TRUE;
        pthread_mutex_unlock(&ota_download_mutex);
        return OPRT_COM_ERROR;
    }
    download->received += len;
    pthread_mutex_unlock(&ota_download_mutex);

    /* Preserve the SDK's per-firmware-type progress route. Installation and
     * its final version report remain owned by the existing update machinery. */
    UINT_T percent = (UINT_T)(((unsigned long long)offset * 100) / ((unsigned long long)total_len + 1));
    tuya_ipc_upgrade_progress_report_by_type(percent, fw->tp);
    return OPRT_OK;
}

INT_T TUYA_IPC_Upgrade_Inform_cb(IN CONST FW_UG_S *fw)
{
    if (fw == NULL || fw->file_size == 0)
    {
        return OPRT_COM_ERROR;
    }
    pthread_mutex_lock(&ota_download_mutex);
    if (ota_download.active || ota_download.starting)
    {
        pthread_mutex_unlock(&ota_download_mutex);
        return OPRT_COM_ERROR;
    }
    memset(&ota_download, 0, sizeof(ota_download));
    ota_download.file = fopen("/tmp/TWO_WIRE_APP", "w+b");
    if (ota_download.file == NULL)
    {
        pthread_mutex_unlock(&ota_download_mutex);
        return OPRT_COM_ERROR;
    }
    ota_download.expected = fw->file_size;
    ota_download.active = TRUE;
    ota_download.starting = TRUE;
    pthread_mutex_unlock(&ota_download_mutex);

    OPERATE_RET result = tuya_ipc_upgrade_sdk(fw, __IPC_APP_get_file_data_cb,
                                             __IPC_APP_upgrade_notify_cb, &ota_download);
    pthread_mutex_lock(&ota_download_mutex);
    /* A synchronous completion may already have closed the file. */
    if (result != OPRT_OK && ota_download.active)
    {
        if (ota_download.file != NULL)
        {
            fclose(ota_download.file);
            ota_download.file = NULL;
        }
        ota_download.active = FALSE;
        unlink("/tmp/TWO_WIRE_APP");
    }
    ota_download.starting = FALSE;
    pthread_mutex_unlock(&ota_download_mutex);
    return result;
}
