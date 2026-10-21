#!/usr/bin/env bash
set -euo pipefail

project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
build_dir="$project_dir/build-tuya6"
toolchain_dir="$project_dir/compilat_tool/arm-anykav500-linux-uclibcgnueabi/bin"

if [[ $# -gt 1 || ( $# -eq 1 && $1 != --build-only ) ]]; then
    echo "Usage: $0 [--build-only]" >&2
    exit 2
fi

cmake -S "$project_dir" -B "$build_dir" \
    -DCMAKE_C_COMPILER="$toolchain_dir/arm-anykav500-linux-uclibcgnueabi-gcc" \
    -DCMAKE_CXX_COMPILER="$toolchain_dir/arm-anykav500-linux-uclibcgnueabi-g++" \
    -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
cmake --build "$build_dir" --parallel "${BUILD_JOBS:-8}"

if [[ ${1:-} == --build-only ]]; then
    echo "Firmware: $build_dir/src/ANYKA37E.BIN"
    exit 0
fi

stage_dir=$(mktemp -d "$build_dir/package.XXXXXX")
trap 'rm -rf -- "$stage_dir"' EXIT
mkdir -p "$stage_dir/app" "$stage_dir/platform"
cp -a "$project_dir/upgrade/app/." "$stage_dir/app/"
cp -a "$project_dir/upgrade/platform/." "$stage_dir/platform/"
cp "$build_dir/src/ANYKA37E.BIN" "$stage_dir/app/ANYKA37E.BIN"
cp "$build_dir/src/rom.bin" "$stage_dir/app/rom.bin"
cp "$project_dir/upgrade/language/bcom/gvs/language.xls" "$stage_dir/app/language.xls"
if [[ -d "$stage_dir/app/rings" ]]; then
    mv "$stage_dir/app/rings" "$stage_dir/original-rings"
fi
cp -a "$project_dir/upgrade/ring/normal/rings" "$stage_dir/app/rings"
"$project_dir/upgrade/tools/mksquashfs" "$stage_dir/app" "$stage_dir/app.sqsh4" \
    -noappend -comp xz -processors "${BUILD_JOBS:-8}"
mv "$stage_dir/app.sqsh4" "$stage_dir/platform/app.sqsh4"
cp "$project_dir/upgrade/scripts/update.sh" "$stage_dir/platform/update.sh"
cp "$project_dir/upgrade/upgrade_progress/upgrade_progress" "$stage_dir/platform/upgrade_progress"

package_name="SAT_ANYKAOS_$(date +%m%d%H%M)"
tar -czf "$stage_dir/$package_name.tmp" -C "$stage_dir/platform" .
mv -fT -- "$stage_dir/$package_name.tmp" "$project_dir/$package_name"
# Remove earlier generated packages only after the new package is in place.
for old_package in "$project_dir"/SAT_ANYKAOS_*; do
    if [[ -f "$old_package" && ! -L "$old_package" &&
          ${old_package##*/} =~ ^SAT_ANYKAOS_([0-9]{8}|[0-9]{10})$ &&
          "$old_package" != "$project_dir/$package_name" ]]; then
        rm -f -- "$old_package"
    fi
done
echo "Firmware: $build_dir/src/ANYKA37E.BIN"
echo "Upgrade package: $project_dir/$package_name"
