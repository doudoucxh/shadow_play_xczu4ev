$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Split-Path -Parent $scriptDir
$xsaPath = Join-Path $rootDir 'Shadow_ultra.xsa'
$bitPath = Join-Path $rootDir 'build\system_wrapper.bit'
$tempPath = Join-Path $rootDir 'Shadow_ultra.packaging.xsa'

if (-not (Test-Path -LiteralPath $xsaPath -PathType Leaf)) {
    throw "Missing XSA: $xsaPath"
}
if (-not (Test-Path -LiteralPath $bitPath -PathType Leaf)) {
    throw "Missing bitstream: $bitPath"
}

Copy-Item -LiteralPath $xsaPath -Destination $tempPath -Force
$archive = [System.IO.Compression.ZipFile]::Open(
    $tempPath,
    [System.IO.Compression.ZipArchiveMode]::Update)
try {
    $oldBit = $archive.GetEntry('Shadow_ultra.bit')
    if ($null -ne $oldBit) {
        $oldBit.Delete()
    }
    [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
        $archive,
        $bitPath,
        'Shadow_ultra.bit',
        [System.IO.Compression.CompressionLevel]::Optimal) | Out-Null

    $xmlEntry = $archive.GetEntry('xsa.xml')
    if ($null -eq $xmlEntry) {
        throw 'xsa.xml is missing from the XSA archive'
    }
    $reader = New-Object System.IO.StreamReader($xmlEntry.Open())
    try {
        [xml]$xml = $reader.ReadToEnd()
    } finally {
        $reader.Dispose()
    }
    $files = $xml.SelectSingleNode('/Root/DSA/Files')
    if ($null -eq $files) {
        throw 'Files element is missing from xsa.xml'
    }
    while ($files.HasChildNodes) {
        $files.RemoveChild($files.FirstChild) | Out-Null
    }
    $fileNode = $xml.CreateElement('File')
    $fileNode.SetAttribute('Type', 'FULL_BIT')
    $fileNode.SetAttribute('Name', 'Shadow_ultra.bit')
    $files.AppendChild($fileNode) | Out-Null
    $xmlEntry.Delete()
    $newXmlEntry = $archive.CreateEntry(
        'xsa.xml',
        [System.IO.Compression.CompressionLevel]::Optimal)
    $writer = New-Object System.IO.StreamWriter($newXmlEntry.Open())
    try {
        $xml.Save($writer)
    } finally {
        $writer.Dispose()
    }
} finally {
    $archive.Dispose()
}

$verify = [System.IO.Compression.ZipFile]::OpenRead($tempPath)
try {
    if ($null -eq $verify.GetEntry('Shadow_ultra.bit')) {
        throw 'Packaged XSA has no Shadow_ultra.bit entry'
    }
    if ($null -eq $verify.GetEntry('system.hwh')) {
        throw 'Packaged XSA has no system.hwh entry'
    }
} finally {
    $verify.Dispose()
}

Move-Item -LiteralPath $tempPath -Destination $xsaPath -Force
Write-Output "PASS: $xsaPath now contains Shadow_ultra.bit"
