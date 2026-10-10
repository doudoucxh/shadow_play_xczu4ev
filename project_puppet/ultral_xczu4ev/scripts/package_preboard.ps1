[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

function Get-Sha256 {
    param([Parameter(Mandatory = $true)][string]$Path)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try {
        $stream = [IO.File]::OpenRead($Path)
        try {
            return ([BitConverter]::ToString($algorithm.ComputeHash($stream))).Replace('-', '').ToLowerInvariant()
        } finally {
            $stream.Dispose()
        }
    } finally {
        $algorithm.Dispose()
    }
}

function Get-PackagePin {
    param(
        [Parameter(Mandatory = $true)][string]$XdcText,
        [Parameter(Mandatory = $true)][string]$Port
    )
    $escaped = [Regex]::Escape($Port)
    $pattern = "PACKAGE_PIN\s+([A-Z]+[0-9]+)[^\r\n]*\[get_ports\s+\{?${escaped}\}?\]"
    $match = [Regex]::Match($XdcText, $pattern)
    if (-not $match.Success) {
        return $null
    }
    return $match.Groups[1].Value
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$repositoryRoot = Split-Path -Parent $projectRoot
$packageRoot = Join-Path $repositoryRoot 'deploy\artifacts\preboard'
$reportRoot = Join-Path $repositoryRoot 'deploy\reports'
$workspace = if ($env:VITIS_WORKSPACE) {
    [IO.Path]::GetFullPath($env:VITIS_WORKSPACE)
} else {
    Join-Path $projectRoot 'vitis_workspace_2022_2'
}
$bootRoot = Join-Path $workspace 'Shadow_ultra_platform\export\Shadow_ultra_platform\sw\Shadow_ultra_platform\boot'

$inputs = [ordered]@{
    'best.pt' = Join-Path $repositoryRoot 'best.pt'
    'system_wrapper.bit' = Join-Path $projectRoot 'build\system_wrapper.bit'
    'Shadow_ultra.xsa' = Join-Path $projectRoot 'Shadow_ultra.xsa'
    'fsbl.elf' = Join-Path $bootRoot 'fsbl.elf'
    'pmufw.elf' = Join-Path $bootRoot 'pmufw.elf'
    'ov5640_hdmi_ultra.elf' = Join-Path $workspace 'ov5640_hdmi_ultra\Debug\ov5640_hdmi_ultra.elf'
    'model_manifest.json' = Join-Path $repositoryRoot 'deploy\artifacts\model_manifest.json'
    'deployment_consistency.json' = Join-Path $reportRoot 'deployment_consistency.json'
    'hls_csim_consistency.json' = Join-Path $reportRoot 'hls_csim_consistency.json'
    'camera_dvp.xdc' = Join-Path $projectRoot 'constraints\camera_dvp.xdc'
    'hdmi.xdc' = Join-Path $projectRoot 'constraints\hdmi.xdc'
}
foreach ($entry in $inputs.GetEnumerator()) {
    if (-not (Test-Path -LiteralPath $entry.Value -PathType Leaf)) {
        throw "Pre-board artifact is missing: $($entry.Value)"
    }
}

New-Item -ItemType Directory -Force -Path $packageRoot | Out-Null
$artifactRows = [ordered]@{}
foreach ($entry in $inputs.GetEnumerator()) {
    $destination = Join-Path $packageRoot $entry.Key
    Copy-Item -LiteralPath $entry.Value -Destination $destination -Force
    $file = Get-Item -LiteralPath $destination
    $artifactRows[$entry.Key] = [ordered]@{
        bytes = $file.Length
        sha256 = Get-Sha256 $destination
        source = $entry.Value
    }
}

$expectedCamera = [ordered]@{
    'cam_pclk' = 'A15'
    'cam_rst_n' = 'A10'
    'cam_pwdn' = 'B15'
    'cam_flash' = 'B14'
    'cam_data[0]' = 'B10'
    'cam_data[1]' = 'B11'
    'cam_data[2]' = 'C11'
    'cam_data[3]' = 'C12'
    'cam_data[4]' = 'A11'
    'cam_data[5]' = 'D12'
    'cam_data[6]' = 'A12'
    'cam_data[7]' = 'A14'
    'cam_vsync' = 'D11'
    'cam_href' = 'E12'
    'cam_scl' = 'D10'
    'cam_sda' = 'E10'
}
$cameraText = Get-Content -LiteralPath $inputs['camera_dvp.xdc'] -Raw
$cameraPins = [ordered]@{}
$cameraMismatches = @()
foreach ($entry in $expectedCamera.GetEnumerator()) {
    $actual = Get-PackagePin -XdcText $cameraText -Port $entry.Key
    $cameraPins[$entry.Key] = $actual
    if ($actual -ne $entry.Value) {
        $cameraMismatches += [ordered]@{
            port = $entry.Key
            expected = $entry.Value
            actual = $actual
        }
    }
}

$expectedHdmi = [ordered]@{
    'tmds_data_p[2]' = 'G3'
    'tmds_data_p[1]' = 'F2'
    'tmds_data_p[0]' = 'G1'
    'tmds_clk_p' = 'E1'
}
$hdmiText = Get-Content -LiteralPath $inputs['hdmi.xdc'] -Raw
$hdmiMismatches = @()
foreach ($entry in $expectedHdmi.GetEnumerator()) {
    $actual = Get-PackagePin -XdcText $hdmiText -Port $entry.Key
    if ($actual -ne $entry.Value) {
        $hdmiMismatches += [ordered]@{
            port = $entry.Key
            expected = $entry.Value
            actual = $actual
        }
    }
}

$modelManifest = [IO.File]::ReadAllText($inputs['model_manifest.json'], [Text.Encoding]::UTF8) | ConvertFrom-Json
$consistency = [IO.File]::ReadAllText($inputs['deployment_consistency.json'], [Text.Encoding]::UTF8) | ConvertFrom-Json
$hlsConsistency = [IO.File]::ReadAllText($inputs['hls_csim_consistency.json'], [Text.Encoding]::UTF8) | ConvertFrom-Json
$expectedModelSha = '01c852378a963ddec52b457d88bc4af2e03aef57847533afd5213d4a6855eb1c'
if ($artifactRows['best.pt'].sha256 -ne $expectedModelSha -or
    $modelManifest.checkpoint_sha256 -ne $expectedModelSha) {
    throw 'The packaged checkpoint or model manifest is not the approved latest V2 model.'
}
if (-not $consistency.fp32_to_fixed_int8.pass -or -not $hlsConsistency.pass) {
    throw 'Host-side deployment consistency checks are not passing.'
}

$vitisRoot = if ($env:XILINX_VITIS) { $env:XILINX_VITIS } else { 'D:\xilinx\Vitis\2022.2' }
$aarch64Tools = Join-Path $vitisRoot 'gnu\aarch64\nt\aarch64-none\bin'
$readelf = Join-Path $aarch64Tools 'aarch64-none-elf-readelf.exe'
$stringsTool = Join-Path $aarch64Tools 'aarch64-none-elf-strings.exe'
foreach ($tool in @($readelf, $stringsTool)) {
    if (-not (Test-Path -LiteralPath $tool -PathType Leaf)) {
        throw "Required AArch64 inspection tool is missing: $tool"
    }
}
$elfPath = $inputs['ov5640_hdmi_ultra.elf']
$elfHeader = (& $readelf -h $elfPath) -join "`n"
if ($LASTEXITCODE -ne 0 -or
    $elfHeader -notmatch 'Class:\s+ELF64' -or
    $elfHeader -notmatch 'Data:\s+2.s complement, little endian' -or
    $elfHeader -notmatch 'Machine:\s+AArch64') {
    throw 'Packaged application is not a little-endian AArch64 ELF64 executable.'
}
$programHeaders = (& $readelf -lW $elfPath) -join "`n"
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to inspect application program headers.'
}
$loadMatches = [Regex]::Matches(
    $programHeaders,
    '(?m)^\s*LOAD\s+0x[0-9a-f]+\s+0x[0-9a-f]+\s+0x([0-9a-f]+)\s+0x[0-9a-f]+\s+0x([0-9a-f]+)'
)
if ($loadMatches.Count -eq 0) {
    throw 'Application ELF contains no loadable segment.'
}
[UInt64]$elfLoadStart = [UInt64]::MaxValue
[UInt64]$elfLoadEnd = 0
foreach ($match in $loadMatches) {
    $physical = [Convert]::ToUInt64($match.Groups[1].Value, 16)
    $memorySize = [Convert]::ToUInt64($match.Groups[2].Value, 16)
    if ($physical -lt $elfLoadStart) { $elfLoadStart = $physical }
    if (($physical + $memorySize) -gt $elfLoadEnd) { $elfLoadEnd = $physical + $memorySize }
}
if ($elfLoadEnd -gt 0x01000000) {
    throw ('Application ELF overlaps the first video buffer: load end 0x{0:X}' -f $elfLoadEnd)
}
$elfStrings = (& $stringsTool $elfPath) -join "`n"
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to inspect application strings.'
}
foreach ($requiredText in @($expectedModelSha, 'POSE_STATUS', 'POSE_PL_FAILURE', 'backend=PL')) {
    if (-not $elfStrings.Contains($requiredText)) {
        throw "Application ELF is missing required validation marker: $requiredText"
    }
}
$bitstreamAfterCameraXdc = (Get-Item -LiteralPath $inputs['system_wrapper.bit']).LastWriteTimeUtc -ge
    (Get-Item -LiteralPath $inputs['camera_dvp.xdc']).LastWriteTimeUtc
$xsaAfterBitstream = (Get-Item -LiteralPath $inputs['Shadow_ultra.xsa']).LastWriteTimeUtc -ge
    (Get-Item -LiteralPath $inputs['system_wrapper.bit']).LastWriteTimeUtc
$readyForJtag = ($cameraMismatches.Count -eq 0) -and $bitstreamAfterCameraXdc -and $xsaAfterBitstream

$manifest = [ordered]@{
    schema_version = 1
    generated_at = (Get-Date).ToString('o')
    target = [ordered]@{
        board = 'ALINX MPSoC-P4 DFZU4EV'
        part = 'xczu4ev-sfvc784-2-i'
        toolchain = 'Vitis 2022.2'
        processor = 'psu_cortexa53_0 standalone'
    }
    status = [ordered]@{
        software_preboard_complete = $true
        ready_for_physical_jtag = $readyForJtag
        board_access_performed = $false
        bitstream_rebuilt = $bitstreamAfterCameraXdc
        camera_pin_check = if ($cameraMismatches.Count -eq 0) { 'pass' } else { 'fail' }
        hdmi_pin_check = if ($hdmiMismatches.Count -eq 0) { 'pass' } else { 'fail' }
        bitstream_after_camera_xdc = $bitstreamAfterCameraXdc
        xsa_after_bitstream = $xsaAfterBitstream
        calibration_kind = $consistency.calibration_kind
        physical_fpga_samples = $consistency.fixed_int8_to_fpga.samples
    }
    model = [ordered]@{
        architecture = 'TinyUpperPoseNetV2'
        checkpoint_sha256 = $expectedModelSha
        input = @(1, 3, 144, 256)
        output = @(1, 9, 36, 64)
    }
    memory_map = [ordered]@{
        elf_load_start = ('0x{0:X8}' -f $elfLoadStart)
        elf_load_end_exclusive = ('0x{0:X8}' -f $elfLoadEnd)
        capture_buffers_start = '0x01000000'
        display_buffers_start = '0x01800000'
        pose_input_working = '0x02000000'
        pose_result = '0x02200000'
        input_snapshot = '0x02300000'
        heatmap_snapshot = '0x02400000'
    }
    verification = [ordered]@{
        fp32_to_int8_pass = [bool]$consistency.fp32_to_fixed_int8.pass
        fp32_to_int8_mean_px = $consistency.fp32_to_fixed_int8.aggregate.mean_px
        fp32_to_int8_fraction_le_8px = $consistency.fp32_to_fixed_int8.aggregate.fraction_le_8px
        hls_csim_heatmap_exact = [bool]$hlsConsistency.pass
        hls_csim_mismatch_bytes = $hlsConsistency.mismatch_bytes
        physical_fpga_pending = $true
    }
    board_constraint_audit = [ordered]@{
        expected_camera_connector = 'user-specified ATK-OV5640 single-camera mapping on J19 pins 4..19'
        expected_camera_pins = $expectedCamera
        actual_camera_pins = $cameraPins
        camera_mismatches = $cameraMismatches
        hdmi_mismatches = $hdmiMismatches
        action_required = if ($readyForJtag) {
            $null
        } else {
            'Confirm primary or secondary OV5640 connector, correct camera_dvp.xdc, then rebuild bitstream and XSA before JTAG.'
        }
    }
    artifacts = $artifactRows
}

$manifestPath = Join-Path $packageRoot 'preboard_manifest.json'
$manifest | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $manifestPath -Encoding utf8
Write-Output "manifest=$manifestPath"
Write-Output "camera_pin_mismatches=$($cameraMismatches.Count)"
Write-Output "hdmi_pin_mismatches=$($hdmiMismatches.Count)"
Write-Output "ready_for_physical_jtag=$readyForJtag"
Write-Output 'PASS: pre-board software artifacts were packaged and hashed.'
