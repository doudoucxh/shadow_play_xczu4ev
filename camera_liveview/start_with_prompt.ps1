param([string]$CameraIP = '192.168.31.250',
      [ValidateRange(10,86400)][int]$Seconds = 28800,
      [ValidateRange(1,15)][int]$FramesPerSecond = 15)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$form = New-Object Windows.Forms.Form
$form.Text = 'Sony 相机访问认证'
$form.ClientSize = New-Object Drawing.Size(470,240)
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.TopMost = $true
$help = New-Object Windows.Forms.Label
$help.Text = "相机已连通，请填写相机菜单中的访问认证信息。`n网络 → 网络选项 → 访问身份验证信息`n此处填写相机认证，不是板端账户。密码仅在内存中传递。"
$help.Location = New-Object Drawing.Point(18,15)
$help.Size = New-Object Drawing.Size(435,68)
$form.Controls.Add($help)
$userLabel = New-Object Windows.Forms.Label
$userLabel.Text = '相机用户名'
$userLabel.Location = New-Object Drawing.Point(20,96)
$form.Controls.Add($userLabel)
$userBox = New-Object Windows.Forms.TextBox
$userBox.Location = New-Object Drawing.Point(125,92)
$userBox.Width = 315
$form.Controls.Add($userBox)
$passwordLabel = New-Object Windows.Forms.Label
$passwordLabel.Text = '相机密码'
$passwordLabel.Location = New-Object Drawing.Point(20,141)
$form.Controls.Add($passwordLabel)
$passwordBox = New-Object Windows.Forms.TextBox
$passwordBox.Location = New-Object Drawing.Point(125,137)
$passwordBox.Width = 315
$passwordBox.UseSystemPasswordChar = $true
$form.Controls.Add($passwordBox)
$connect = New-Object Windows.Forms.Button
$connect.Text = '连接取景'
$connect.Location = New-Object Drawing.Point(260,190)
$connect.DialogResult = [Windows.Forms.DialogResult]::OK
$form.Controls.Add($connect)
$cancel = New-Object Windows.Forms.Button
$cancel.Text = '取消'
$cancel.Location = New-Object Drawing.Point(365,190)
$cancel.DialogResult = [Windows.Forms.DialogResult]::Cancel
$form.Controls.Add($cancel)
$form.AcceptButton = $connect
$form.CancelButton = $cancel
$form.Add_Shown({ $userBox.Focus() })
$credential = $null
try {
    while ($form.ShowDialog() -eq [Windows.Forms.DialogResult]::OK) {
        if ([string]::IsNullOrWhiteSpace($userBox.Text) -or [string]::IsNullOrEmpty($passwordBox.Text)) {
            [void][Windows.Forms.MessageBox]::Show('请输入相机访问认证的用户名和密码。','认证信息未填写')
            continue
        }
        $secure = ConvertTo-SecureString $passwordBox.Text -AsPlainText -Force
        $credential = [Management.Automation.PSCredential]::new($userBox.Text.Trim(),$secure)
        break
    }
} finally {
    $passwordBox.Clear()
    $form.Dispose()
}
if ($credential) {
    try {
        & (Join-Path $PSScriptRoot 'start_liveview.ps1') -CameraIP $CameraIP -Seconds $Seconds -FramesPerSecond $FramesPerSecond -CameraCredential $credential
    } finally {
        $credential.Password.Dispose()
    }
}
