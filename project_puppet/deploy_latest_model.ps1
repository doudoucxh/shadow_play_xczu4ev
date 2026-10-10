param(
    [string]$CalibrationDir = '.\deploy\board_calibration',
    [ValidateSet('board_roi', 'provisional_images')]
    [string]$CalibrationKind = 'board_roi',
    [switch]$SkipBuild,
    [switch]$Program
)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$CalibrationDir = if ([IO.Path]::IsPathRooted($CalibrationDir)) { $CalibrationDir } else { Join-Path $projectRoot $CalibrationDir }
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$exporter = Join-Path $projectRoot 'tools\export_pose_hls.py'
$vitisCheck = Join-Path $projectRoot 'ultral_xczu4ev\scripts\check_vitis_2022_2.ps1'
if (!(Test-Path -LiteralPath $python)) { throw "Missing isolated Python environment: $python" }
if (!(Test-Path -LiteralPath $CalibrationDir)) { throw "Missing calibration directory: $CalibrationDir" }

& $python $exporter --calibration-dir $CalibrationDir --calibration-count 200 --calibration-kind $CalibrationKind
if ($LASTEXITCODE -ne 0) { throw 'Model export failed.' }

if (!$SkipBuild) {
    & $vitisCheck
    if ($LASTEXITCODE -ne 0) { throw 'Vitis preflight failed.' }
    & (Join-Path $projectRoot 'ultral_xczu4ev\build_firmware.bat')
    if ($LASTEXITCODE -ne 0) { throw 'A53 firmware build failed.' }
}
if ($Program) {
    & (Join-Path $projectRoot 'ultral_xczu4ev\program_and_run.bat')
    if ($LASTEXITCODE -ne 0) { throw 'JTAG deployment failed.' }
}
