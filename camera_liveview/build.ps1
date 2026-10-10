$ErrorActionPreference = 'Stop'
$vswhere = 'C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe'
$vsPath = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if(-not $vsPath){throw 'MSVC C++ build tools not found'}
Import-Module (Join-Path $vsPath 'Common7\Tools\Microsoft.VisualStudio.DevShell.dll')
Enter-VsDevShell -VsInstallPath $vsPath -SkipAutomaticLocation -DevCmdArguments '-arch=amd64 -host_arch=amd64' | Out-Null
cmake -S $PSScriptRoot -B (Join-Path $PSScriptRoot 'build') -G Ninja '-DCMAKE_BUILD_TYPE=Release' '-DCMAKE_CXX_COMPILER=cl.exe' '-DCMAKE_TRY_COMPILE_CONFIGURATION=Release'
if($LASTEXITCODE -ne 0){throw 'CMake configure failed'}
cmake --build (Join-Path $PSScriptRoot 'build') --parallel 2
if($LASTEXITCODE -ne 0){throw 'CMake build failed'}
