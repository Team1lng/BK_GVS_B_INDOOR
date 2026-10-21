//
// Created by michael on 2021/11/8.
//

#include "../../include/anyka/ak_thread.h"
#include "../../include/anyka/ak_common.h"
#include <string.h>
#include <unistd.h>
#include <stdio.h>
#include "wlan.h"
#include "../../lvgl/lvgl.h"

#include "tuya_sdk.h"


#include <signal.h>
#include <stdlib.h>
#include "../gpio/gpio_api.h"

static int scanned_wifi_index = 0;
static linked_info wifi_wlan0 = {0};
static wifi_info scanned_wifi[MAX_WIFI_SCAN] = {{"\0", "\0", 0, false, false}};

static bool wifi_usb_enable = true;
#define WIFI_USB_DETECT_PIN 26
bool wifi_usb_module_enable(void)
{
    return wifi_usb_enable;
}

void wifi_usb_module_init(void)
{
    GPIO_LEVEL level = GPIO_LEVEL_UNKNOWN;
    gpio_read(WIFI_USB_DETECT_PIN, &level);
    if (level == GPIO_LEVEL_LOW)
        wifi_usb_enable = false;
    else if (level == GPIO_LEVEL_HIGH)
        wifi_usb_enable = true;

    printf("%s:%d\n", __func__, wifi_usb_enable);
}

bool is_Hisilicon0_paltform(void)
{
    const char *dir_path = "/sys/class/net/Hisilicon0";
    /*如果用的是海思wifi即关闭wifi扫描及列表 */
    if (access(dir_path, F_OK) != -1)
    {
        printf("Directory %s exists.\n", dir_path);
        return true;
    }
    printf("Directory %s does not exist.\n", dir_path);
    return false;
}

static void parsing_data(char *data, int index)
{
    char *p_level = strchr(data, '-');
    char *p_flag = strchr(p_level, '[');
    char *p_ssid = strrchr(p_level, '\t') + 1;

    scanned_wifi[index].hidden = false;
    scanned_wifi[index].free = false;

    char tmp_level[8] = {0};
    char *stop_str;
    strncpy(tmp_level, p_level, p_flag - p_level);
    scanned_wifi[index].signal_level = strtol(tmp_level, &stop_str, 10);
    // printf("level: %d \n\r",scanned_wifi[index].signal_level);

    memset(scanned_wifi[index].flags, 0x00, sizeof(scanned_wifi[index].flags));
    strncpy(scanned_wifi[index].flags, p_flag, p_ssid - p_flag - 1);

    if (strcmp(scanned_wifi[index].flags, "[ESS]") == 0)
    {
        scanned_wifi[index].free = true;
    }
    // printf("flags: %d \n\r",scanned_wifi[index].free);

    memset(scanned_wifi[scanned_wifi_index].ssid, 0x00, sizeof(scanned_wifi[scanned_wifi_index].ssid));

#if 1
    char unresolved[3] = {"\\x"};
    char *ret = strpbrk(p_ssid, unresolved);
    if (ret)
    {
// printf("Unresolved: %s \n\r",p_ssid);
#if 0
        const char *unresolved[8] ={
                "Unresolved","미해결","Irresoluta","Нерешенный","لم تحل","Chưa giải quyết"
        };
        memset(scanned_wifi[scanned_wifi_index].ssid,0,sizeof (scanned_wifi[scanned_wifi_index].ssid));
        sprintf(scanned_wifi[scanned_wifi_index].ssid, "%s",unresolved[0]);//10
#else
        strncpy(scanned_wifi[scanned_wifi_index].ssid, p_ssid, strlen(p_ssid) - 1);
#endif
    }
    else
    {
        if ((strlen(p_ssid) == 1) && (strncmp(p_ssid, "\n", sizeof("\n")) == 0))
        {
            const char *hidden[8] = {
                "Hidden Wi-Fi", "숨겨져 있고 충실한", "Escondido y fiel", "Скрытый и верный", "هيدن وفي", "Giấu kín và trung thành"};
            memset(scanned_wifi[scanned_wifi_index].ssid, 0, sizeof(scanned_wifi[scanned_wifi_index].ssid));
            sprintf(scanned_wifi[scanned_wifi_index].ssid, "%s", hidden[0]); // 12
            scanned_wifi[index].hidden = true;
        }
        else
        {
            strncpy(scanned_wifi[scanned_wifi_index].ssid, p_ssid, strlen(p_ssid) - 1);
        }
    }
#endif
    // printf("ssid: %s \n\r", scanned_wifi[scanned_wifi_index].ssid);
}

static int if_wlan_up(void)
{
    int ret = 0;
    FILE *pf = popen("cat /sys/class/net/wlan0/operstate", "r");
    if (pf == NULL)
    {
        perror("get wlan0 operstate error !\n\r");
        return ret;
    }
    char buffer[256] = {0};
    memset(buffer, 0, sizeof(buffer));
    while (fgets(buffer, sizeof(buffer), pf))
    {
        // printf("buffer: %s \n\r",buffer);
        if (strncmp(buffer, "up", 2) == 0)
        {
            ret = 1;
        }
        else if (strncmp(buffer, "dormant", 7) == 0)
        {
            ret = 2;
        }
        else if (strncmp(buffer, "down", 4) == 0)
        {
            ret = 3;
        }
    }
    pclose(pf);
    pf = NULL;

    return ret;
}

int wpa_cli_scan_wifi(bool *continue_flag)
{
    // system("wpa_cli -i wlan0 scan");
    int ret = if_wlan_up();
    if (ret <= 0)
    {
        printf("-0-\n\r");
        return -1;
    }
    FILE *fp = popen("wpa_cli -i wlan0 scan", "r");
    if (fp == NULL)
    {
        perror("wpa_cli -i wlan0 scan open fail !\n\r");
        return -1;
    }
    char buffer[32] = {0};
    while (fgets(buffer, sizeof(buffer), fp) && (*continue_flag == true))
    {
        printf(">>> [wlan scan: %s ]\n\r", buffer);
        // if (strstr(buffer, "OK") == NULL)
        // {
        //     return;
        // }
    }
    pclose(fp);

    // ak_sleep_ms(300);
    FILE *pf = popen("wpa_cli -i wlan0 scan_result", "r");
    if (pf == NULL)
    {
        perror("wpa_cli_scan_wifi open fail !\n\r");
        return -1;
    }
    char tmp_buffer[1024 * 2] = {0};
    int scanned_index = 0;
    scanned_wifi_index = 0;
    while (fgets(tmp_buffer, sizeof(tmp_buffer), pf) && (*continue_flag == true))
    {
        // printf(" %s \n\r", tmp_buffer);
        if (scanned_index >= 1)
        {

            parsing_data(tmp_buffer, scanned_wifi_index);
            scanned_wifi_index++;
            if (scanned_wifi_index >= MAX_WIFI_SCAN)
            {
                break;
            }
        }
        memset(tmp_buffer, 0, sizeof(tmp_buffer));
        scanned_index++;
    }
    pclose(pf);
    return scanned_wifi_index;
}

bool get_scanned_wifi_info(int index, wifi_info *info)
{
    if ((index < scanned_wifi_index) && (info != NULL))
    {
        *info = scanned_wifi[index];
        return true;
    }
    return false;
}

static bool connectwifi_level(void)
{
    for (int i = 0; i < scanned_wifi_index; i++)
    {
        if (strcmp(wifi_wlan0.wlan_ssid, scanned_wifi[i].ssid) == 0)
        {
            wifi_wlan0.level = scanned_wifi[i].signal_level;
            return true;
        }
    }
    return false;
}

bool wpa_cli_wlan_status(bool *continue_flag)
{

    memset(&wifi_wlan0, 0, sizeof(wifi_wlan0));

    FILE *pf = popen("wpa_cli -i wlan0 status", "r");
    if (pf == NULL)
    {
        perror(" wpa_cli_wlan_status open fail \n\r");
        return false;
    }
    char buffer[1024 * 1] = {0};
    memset(buffer, 0, sizeof(buffer));
    while (fgets(buffer, sizeof(buffer), pf) && (*continue_flag == true))
    {
        if (strncmp(buffer, "ssid=", 5) == 0)
        {
            char *p = strchr(buffer, '=') + 1;
            strncpy(wifi_wlan0.wlan_ssid, p, strlen(p) - 1);
            strcat(wifi_wlan0.wlan_ssid, "\0");
            // printf("1:%s \n\r",wifi_wlan0.wlan_ssid);
        }
        else if (strncmp(buffer, "key_mgmt=", 9) == 0)
        {
            char *p = strchr(buffer, '=') + 1;
            strncpy(wifi_wlan0.key_mgmt, p, strlen(p) - 1);
            strcat(wifi_wlan0.wlan_ssid, "\0");
            // printf("2:%s \n\r",wifi_wlan0.key_mgmt);
        }
        else if (strncmp(buffer, "wpa_state=COMPLETED", 19) == 0)
        {
            wifi_wlan0.completed = 1;
        }
        else if (strncmp(buffer, "ip_address=", 11) == 0)
        {
            char *p = strchr(buffer, '=') + 1;
            strncpy(wifi_wlan0.ip, p, strlen(p) - 1);
            strcat(wifi_wlan0.ip, "\0");
            // printf("3:%s \n\r",wifi_wlan0.ip);
        }
        else if (strncmp(buffer, "address=", 8) == 0)
        {
            char *p = strchr(buffer, '=') + 1;
            strncpy(wifi_wlan0.mac, p, strlen(p) - 1);
            strcat(wifi_wlan0.wlan_ssid, "\0");
            // printf("4:%s \n\r",wifi_wlan0.mac);
        }
    }
    pclose(pf);
    connectwifi_level();
    return true;
}

/* A connection attempt owns its credentials and all network process changes.
 * LVGL only stages credentials, starts the worker and reads its state. */
#define WIFI_TEMP_CONFIG_PATH "/tmp/wpa_supplicant.conf"
typedef struct
{
    unsigned int generation;
    char ssid[128];
    char psk[64];
} wifi_connection_worker_arg;

static pthread_mutex_t wifi_connection_mutex = PTHREAD_MUTEX_INITIALIZER;
static int wifi_connection_check_result = WIFI_CONNECTION_CHECK_IDLE;
static bool wifi_connection_check_running = false;
static unsigned int wifi_connection_check_generation = 0;
static wifi_connection_worker_arg wifi_connection_pending;
static bool wifi_connection_pending_valid = false;

static void restore_saved_wifi_config(void)
{
    system("killall wpa_supplicant");
    system("killall udhcpc");
    unlink(WIFI_TEMP_CONFIG_PATH);
    system("wpa_supplicant -Dnl80211 -i wlan0 -c " WPA_SUPPLICANT_PATH " -B");
    system("udhcpc -i wlan0 -n 4 -R &");
    clear_linked_wifi_info();
}

/* Escape quoted wpa_supplicant values without passing credentials to a shell. */
static bool wifi_config_quote(char *dest, size_t capacity, const char *source)
{
    size_t used = 0;
    while (*source)
    {
        unsigned char value = (unsigned char)*source++;
        if (value < 32 || value == 127 || used + 2 >= capacity)
            return false;
        if (value == '"' || value == '\\')
            dest[used++] = '\\';
        dest[used++] = value;
    }
    dest[used] = '\0';
    return true;
}

static bool wifi_prepare_candidate(const wifi_connection_worker_arg *candidate)
{
    char ssid[256], psk[128];
    if (!wifi_config_quote(ssid, sizeof(ssid), candidate->ssid) ||
        !wifi_config_quote(psk, sizeof(psk), candidate->psk))
        return false;

    FILE *fp = fopen(WIFI_TEMP_CONFIG_PATH, "w");
    if (fp == NULL)
        return false;
    int written;
    if (psk[0])
        written = fprintf(fp, "ctrl_interface=/var/run/wpa_supplicant\nupdate_config=1\nnetwork={\n\tscan_ssid=1\n\tkey_mgmt=WPA-PSK\n\tssid=\"%s\"\n\tpsk=\"%s\"\n}\n", ssid, psk);
    else
        written = fprintf(fp, "ctrl_interface=/var/run/wpa_supplicant\nupdate_config=1\nnetwork={\n\tscan_ssid=1\n\tkey_mgmt=NONE\n\tssid=\"%s\"\n}\n", ssid);
    int closed = fclose(fp);
    if (written < 0 || closed != 0)
        return false;

    system("killall wpa_supplicant");
    system("killall udhcpc");
    clear_linked_wifi_info();
    if (system("wpa_supplicant -Dnl80211 -i wlan0 -c " WIFI_TEMP_CONFIG_PATH " -B") != 0)
        return false;
    system("udhcpc -i wlan0 -n 4 -R &");
    return true;
}

int wifi_connection_status_sucess(void)
{
    int result = 0;
    if (access("/var/run/wpa_supplicant/wlan0", F_OK) != 0)
        return 0;

    FILE *pf = popen("wpa_cli -i wlan0 status 2>/dev/null", "r");
    if (pf == NULL)
    {
        perror("popen failed");
        return 0;
    }

    char buffer[1024 * 10] = {0};
    while (fgets(buffer, sizeof(buffer), pf) != NULL)
    {
        if (strncmp(buffer, "wpa_state=COMPLETED", 19) == 0)
        {
            result = 1;
            break;
        }
    }

    pclose(pf);
    return result;
}

static bool wifi_connection_attempt_active(unsigned int generation)
{
    pthread_mutex_lock(&wifi_connection_mutex);
    bool active = wifi_connection_check_running && generation == wifi_connection_check_generation;
    pthread_mutex_unlock(&wifi_connection_mutex);
    return active;
}

static void *wifi_connection_worker(void *arg)
{
    wifi_connection_worker_arg *candidate = arg;
    unsigned int generation = candidate->generation;
    bool attempted = false;
    bool success = false;

    if (wifi_connection_attempt_active(generation))
    {
        attempted = true;
        if (wifi_prepare_candidate(candidate))
        {
            for (int attempt = 0; attempt < 30; ++attempt)
            {
                if (!wifi_connection_attempt_active(generation))
                    break;
                int connected = wifi_connection_status_sucess();
                pthread_mutex_lock(&wifi_connection_mutex);
                if (connected && generation == wifi_connection_check_generation)
                {
                    /* Replace the saved file only after association succeeds. */
                    success = system("cp " WIFI_TEMP_CONFIG_PATH " " WPA_SUPPLICANT_PATH ".tmp && mv " WPA_SUPPLICANT_PATH ".tmp " WPA_SUPPLICANT_PATH) == 0;
                    if (success)
                    {
                        system("sync");
                        wifi_connection_check_result = WIFI_CONNECTION_CHECK_SUCCESS;
                        wifi_connection_check_running = false;
                    }
                    pthread_mutex_unlock(&wifi_connection_mutex);
                    break;
                }
                pthread_mutex_unlock(&wifi_connection_mutex);
                ak_sleep_ms(500);
            }
        }
    }

    if (!success)
    {
        if (attempted)
            restore_saved_wifi_config();
        pthread_mutex_lock(&wifi_connection_mutex);
        if (generation == wifi_connection_check_generation)
            wifi_connection_check_result = WIFI_CONNECTION_CHECK_FAIL;
        wifi_connection_check_running = false;
        pthread_mutex_unlock(&wifi_connection_mutex);
    }
    memset(candidate, 0, sizeof(*candidate));
    free(candidate);
    ak_thread_exit();
    return NULL;
}

void wpa_cli_connect_new_wifi(char *ssid, char *psk)
{
    pthread_mutex_lock(&wifi_connection_mutex);
    if (!wifi_connection_check_running)
    {
        memset(&wifi_connection_pending, 0, sizeof(wifi_connection_pending));
        wifi_connection_pending_valid = ssid && strlen(ssid) > 0 &&
            strlen(ssid) < sizeof(wifi_connection_pending.ssid) &&
            (!psk || !psk[0] || (strlen(psk) >= 8 && strlen(psk) < sizeof(wifi_connection_pending.psk)));
        if (wifi_connection_pending_valid)
        {
            strcpy(wifi_connection_pending.ssid, ssid);
            if (psk)
                strcpy(wifi_connection_pending.psk, psk);
        }
    }
    pthread_mutex_unlock(&wifi_connection_mutex);
}

bool wifi_connection_check_start(void)
{
    pthread_mutex_lock(&wifi_connection_mutex);
    if (wifi_connection_check_running)
    {
        pthread_mutex_unlock(&wifi_connection_mutex);
        return false;
    }
    wifi_connection_worker_arg *candidate = wifi_connection_pending_valid ? malloc(sizeof(*candidate)) : NULL;
    wifi_connection_pending_valid = false;
    if (candidate == NULL)
    {
        wifi_connection_check_result = WIFI_CONNECTION_CHECK_FAIL;
        pthread_mutex_unlock(&wifi_connection_mutex);
        return false;
    }
    *candidate = wifi_connection_pending;
    memset(&wifi_connection_pending, 0, sizeof(wifi_connection_pending));
    candidate->generation = ++wifi_connection_check_generation;
    wifi_connection_check_result = WIFI_CONNECTION_CHECK_RUNNING;
    wifi_connection_check_running = true;
    ak_pthread_t thread_id;
    if (ak_thread_create(&thread_id, wifi_connection_worker, candidate,
                         ANYKA_THREAD_NORMAL_STACK_SIZE, -1) != 0)
    {
        memset(candidate, 0, sizeof(*candidate));
        free(candidate);
        wifi_connection_check_running = false;
        wifi_connection_check_result = WIFI_CONNECTION_CHECK_FAIL;
        pthread_mutex_unlock(&wifi_connection_mutex);
        return false;
    }
    ak_thread_detach(thread_id);
    pthread_mutex_unlock(&wifi_connection_mutex);
    return true;
}

int wifi_connection_check_state(void)
{
    pthread_mutex_lock(&wifi_connection_mutex);
    int state = wifi_connection_check_result;
    pthread_mutex_unlock(&wifi_connection_mutex);
    return state;
}

void wifi_connection_check_cancel(void)
{
    pthread_mutex_lock(&wifi_connection_mutex);
    ++wifi_connection_check_generation;
    wifi_connection_check_result = WIFI_CONNECTION_CHECK_IDLE;
    wifi_connection_pending_valid = false;
    memset(&wifi_connection_pending, 0, sizeof(wifi_connection_pending));
    /* The worker keeps ownership until rollback finishes; a new attempt must wait. */
    pthread_mutex_unlock(&wifi_connection_mutex);
}

int wpa_cli_check_connect_status(void)
{
    int state = wifi_connection_check_state();
    return state == WIFI_CONNECTION_CHECK_SUCCESS ? 1 : state == WIFI_CONNECTION_CHECK_FAIL ? -2 : 0;
}

int current_wlan_signal_level(void)
{
    int ret = 0;
    char tmp_str[1024];
    memset(tmp_str, 0, 1024);
    FILE *fp = popen("cat /proc/net/wireless |grep wlan0 |awk '{print $4}' ", "r");
    if (fp != NULL)
    {
        if (!feof(fp))
        {
            while (fgets(tmp_str, sizeof(tmp_str), fp))
            {
                char tmp_level[8] = {0};
                char *p_start = strchr(tmp_str, '-');
                char *p_end = strchr(tmp_str, '.');
                strncpy(tmp_level, tmp_str, p_end - p_start);
                printf("Signal Level: %s dB\n\r", tmp_level);
                int level = atoi(tmp_level);
                return level;
            }
        }
    }
    pclose(fp);
    return ret;
}

static ak_pthread_t wlan_thread_id;
static bool wlan_thread_run = false;
static bool wlan_turn_on = false;

void clear_linked_wifi_info(void)
{
    memset(&wifi_wlan0, 0, sizeof(wifi_wlan0));
}

void get_linked_wifi_info(linked_info *info)
{
    *info = wifi_wlan0;
}
/*
static bool wlan_udhcpc_status(bool *continue_flag){

    system("killall udhcpc");
    bool ret = false;
    FILE *pf = popen("udhcpc -i wlan0 -n 4 -R &","r");

    if(pf == NULL){
        perror("udhcpc -i wlan0 error !\n\r");
        return ret;
    }
     char buffer[256] = {0};
    memset(buffer,0,sizeof (buffer));
    while(fgets(buffer,sizeof (buffer),pf) && (*continue_flag == true)){

        printf("buffer: %s \n\r",buffer);
        if(strncmp(buffer,"adding dns ",11) == 0){
            char *p = strchr(buffer,'s') + 1;
            printf("DNS: %s \n\r",p);
            ret = true;
        }
    }
    pclose(pf);
    pf = NULL;
    return ret;
}
*/

void printf_connected_info(void)
{
    if (wifi_wlan0.completed)
    {
        wifi_wlan0.level = current_wlan_signal_level();
        printf("ssid: %s\n\r", wifi_wlan0.wlan_ssid);
        printf("mac: %s \n\r", wifi_wlan0.mac);
        printf("ip: %s \n\r", wifi_wlan0.ip);
        printf("key_mgmt %s \n\r", wifi_wlan0.key_mgmt);
        printf("level: %d  \n\r", wifi_wlan0.level);
    }
}

static void kill_background_thread(void)
{

    system("killall wpa_supplicant");
    system("killall udhcpc");
}
static void start_connect_process(void)
{
    char cmd[128] = {0};
    snprintf(cmd, sizeof(cmd), "wpa_supplicant -Dnl80211 -i wlan0 -c %s -B &", WPA_SUPPLICANT_PATH);
    system(cmd);
}

static void *check_wlan_task(void *arg)
{
    bool run_once_flag = false;
    bool connected_info_active = false;
    scanned_wifi_index = 0;

    signal(SIGCHLD, SIG_IGN);

    kill_background_thread();
    bool *run = (bool *)arg;

    int udhcpc_cnt = 0;
    while (*run)
    {
        if (wlan_turn_on)
        {
            // Once: start connect wi-fi
            if (run_once_flag == false)
            {
                start_connect_process();
                system("udhcpc -i wlan0 -n 4 -R &");
                udhcpc_cnt = 50;
                run_once_flag = true;
                printf("udhcpc -i wlan0 -n 4 -R & !\n\r");
            }
            else if (connected_info_active == false)
            {
                // Get udhcpc status
                if (if_wlan_up() == 1)
                {

                    // Update connected wi-fi info
                    scanned_wifi_index = wpa_cli_scan_wifi(&wlan_turn_on);
                    wpa_cli_wlan_status(&wlan_turn_on);
                    printf_connected_info();
                    connected_info_active = true;
                }
                else
                {
                    connected_info_active = false;
                    if (if_wlan_up() == 2 || if_wlan_up() == 3)
                    {
                        if (scanned_wifi_index == 0)
                        {
                            // printf("---%s------%d-----\n\r",__func__ ,__LINE__);
                            scanned_wifi_index = wpa_cli_scan_wifi(&wlan_turn_on);
                        }
                        if (udhcpc_cnt && (--udhcpc_cnt == 0))
                        {
                            system("killall udhcpc");
                            // printf("---%s------%d-----\n\r",__func__ ,__LINE__);
                        }
                    }
                }
            }
            else if (connected_info_active == true)
            {
                if (scanned_wifi_index == 0)
                {
                    // printf("---%s------%d-----\n\r",__func__ ,__LINE__);
                    wpa_cli_wlan_status(&wlan_turn_on);
                    scanned_wifi_index = wpa_cli_scan_wifi(&wlan_turn_on);
                }
            }
            else
            {
                printf("---%s------%d-----\n\r", __func__, __LINE__);
            }
        }
        else
        {
            if (connected_info_active == true)
            {
                // printf("---%s------%d-----\n\r",__func__ ,__LINE__);
                scanned_wifi_index = 0;
                connected_info_active = false;
                run_once_flag = false;
                // printf("---%s------%d-----\n\r",__func__ ,__LINE__);
                kill_background_thread();
                // printf("---%s------%d-----\n\r",__func__ ,__LINE__);
                ak_sleep_ms(500);
            }
            else if (if_wlan_up() && run_once_flag)
            {
                // printf("---%s------%d-----\n\r",__func__ ,__LINE__);
                scanned_wifi_index = 0;
                connected_info_active = false;
                run_once_flag = false;
                kill_background_thread();
            }
        }
        ak_sleep_ms(200);
    }
    printf("!!!!!--- DA MIE ----!!!!!\n\r");
    *run = false;
    ak_thread_exit();
    return NULL;
}

bool create_check_wlan_task(void)
{
    if (wlan_thread_run)
    {
        return false;
    }
    wlan_thread_run = true;
    ak_thread_create(&wlan_thread_id, check_wlan_task, &wlan_thread_run, ANYKA_THREAD_NORMAL_STACK_SIZE, -1);
    return true;
}

bool destroy_check_wlan_task(void)
{
    if (wlan_thread_run == false)
    {
        return false;
    }
    wlan_thread_run = false;
    ak_thread_join(wlan_thread_id);
    wlan_thread_id = 0;
    return true;
}

void update_wifi_list(void)
{
    scanned_wifi_index = 0;
}

int get_max_wifi_list_index(void)
{
    return scanned_wifi_index;
}

void turn_on_wlan_connect(void)
{
    wlan_turn_on = true;
    start_connect_process();
    system("udhcpc -i wlan0 -n 4 -R &");
    update_wifi_list();
}

void turn_off_wlan_connect(void)
{
    wlan_turn_on = false;
    kill_background_thread(); // 关闭wifi的客户端和服务器
}

void turn_on_walan_reconnect(void)
{

    // system("wpa_cli -i wlan0 enable_network 0");
    // printf("############wlan0 up!\n");
    system("wpa_cli -i wlan0 reconnect");
    printf("$$$$$$$$$$$$$$$$$$udhcpc wlan0!\n");
    // update_wifi_list();
}

/* Match configuration keys only, never text inside SSIDs, keys or comments. */
static const char *wlan_config_value(const char *line, const char *key)
{
    line += strspn(line, " \t");
    size_t key_length = strlen(key);
    if (strncmp(line, key, key_length) != 0)
        return NULL;
    line += key_length;
    line += strspn(line, " \t");
    if (*line++ != '=')
        return NULL;
    return line + strspn(line, " \t");
}

static bool wlan_config_line_end(const char *line)
{
    line += strspn(line, " \t\r\n");
    return *line == '\0' || *line == '#';
}

static bool wlan_config_network_end(const char *line)
{
    line += strspn(line, " \t");
    return *line == '}' && wlan_config_line_end(line + 1);
}

static bool wlan_config_all_networks_disabled(FILE *config)
{
    char *line = NULL;
    size_t capacity = 0;
    bool in_network = false;
    bool disabled = false;
    bool found_network = false;
    bool valid = true;

    while (getline(&line, &capacity, config) >= 0)
    {
        const char *value = wlan_config_value(line, "network");
        if (!in_network && value && *value == '{' && wlan_config_line_end(value + 1))
        {
            in_network = true;
            disabled = false;
            found_network = true;
        }
        else if (in_network && (value = wlan_config_value(line, "disabled")) != NULL)
        {
            disabled = *value == '1' && wlan_config_line_end(value + 1);
        }
        else if (in_network && wlan_config_network_end(line))
        {
            if (!disabled)
                valid = false;
            in_network = false;
        }
    }
    free(line);
    return found_network && valid && !in_network && !ferror(config);
}

static bool disable_wlan_networks_in_config(void)
{
    char temp_path[256] = {0};
    char *config_line = NULL;
    size_t capacity = 0;
    bool in_network = false;
    bool disabled_written = false;
    int disabled_network_count = 0;

    snprintf(temp_path, sizeof(temp_path), "%s.tmp", WPA_SUPPLICANT_PATH);
    FILE *source_file = fopen(WPA_SUPPLICANT_PATH, "r");
    if (source_file == NULL)
        return false;
    FILE *temp_file = fopen(temp_path, "w");
    if (temp_file == NULL)
    {
        fclose(source_file);
        return false;
    }

    /* Read whole lines so a long quoted value cannot become a setting fragment. */
    while (getline(&config_line, &capacity, source_file) >= 0)
    {
        const char *value = wlan_config_value(config_line, "network");
        if (!in_network && value && *value == '{' && wlan_config_line_end(value + 1))
        {
            in_network = true;
            disabled_written = false;
        }
        else if (in_network && (value = wlan_config_value(config_line, "disabled")) != NULL)
        {
            /* Preserve indentation, key spacing and trailing comments. */
            fwrite(config_line, 1, value - config_line, temp_file);
            fputc('1', temp_file);
            value += strcspn(value, " \t\r\n#");
            fputs(value, temp_file);
            disabled_written = true;
            continue;
        }
        else if (in_network && wlan_config_network_end(config_line))
        {
            if (!disabled_written)
                fputs(strstr(config_line, "\r\n") ? "\tdisabled=1\r\n" : "\tdisabled=1\n", temp_file);
            disabled_network_count++;
            in_network = false;
        }
        fputs(config_line, temp_file);
    }
    free(config_line);

    bool saved = !in_network && !ferror(source_file) && !ferror(temp_file);
    if (fflush(temp_file) != 0 || fsync(fileno(temp_file)) != 0)
        saved = false;
    if (fclose(temp_file) != 0)
        saved = false;
    if (fclose(source_file) != 0)
        saved = false;
    if (!saved || rename(temp_path, WPA_SUPPLICANT_PATH) != 0)
    {
        unlink(temp_path);
        return false;
    }

    system("sync");
    printf("WiFi config force-disabled network count: %d\n", disabled_network_count);
    return true;
}

static void disable_wlan_networks_and_save(void)
{
    FILE *network_file;
    char network_id[32] = {0};
    char command[128] = {0};
    int disabled_network_count = 0;

    system("wpa_cli -i wlan0 disable_network all");

    network_file = popen("wpa_cli -i wlan0 list_networks | awk '$1 ~ /^[0-9]+$/ {print $1}'", "r");
    if (network_file != NULL)
    {
        while (fgets(network_id, sizeof(network_id), network_file) != NULL)
        {
            network_id[strcspn(network_id, "\r\n")] = '\0';
            if (network_id[0] == '\0')
            {
                continue;
            }

            snprintf(command, sizeof(command), "wpa_cli -i wlan0 set_network %s disabled 1", network_id);
            system(command);
            disabled_network_count++;
        }
        pclose(network_file);
    }

    system("wpa_cli -i wlan0 save_config");
    disable_wlan_networks_in_config();

    network_file = fopen(WPA_SUPPLICANT_PATH, "r");
    if (network_file == NULL)
    {
        printf("WiFi config open failed after disable: %s\n", WPA_SUPPLICANT_PATH);
        return;
    }

    bool disabled_saved = wlan_config_all_networks_disabled(network_file);
    fclose(network_file);

    printf("WiFi disabled network count: %d, config saved: %d\n", disabled_network_count, disabled_saved ? 1 : 0);
}

void turn_off_wlan_break(void)
{
    wifi_connection_check_cancel();
    wlan_turn_on = false;
    system("killall udhcpc");
    disable_wlan_networks_and_save();
    system("wpa_cli -i wlan0 disconnect");
    clear_linked_wifi_info();
    printf("@@@@@@@@@@@wlan0 down!\n");
}

void CloseConnectingWifi(void)
{

    system("ifconfig wlan0 down");
}

void StartConnectingWifi(void)
{
    system("ifconfig wlan0 up");

    system("killall udhcpc");
    system("udhcpc -b -i wlan0 &");
}
