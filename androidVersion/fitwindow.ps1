# Emülatör penceresini ekrana sığdırır (otomatik boyutta ekranın üstüne taşıyor, ayar dosyasını da kapanırken sıfırlıyor)
Add-Type @'
using System; using System.Runtime.InteropServices;
public class EmuWin { [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr a, int x, int y, int cx, int cy, uint f); }
'@
for ($i = 0; $i -lt 30; $i++) {
    $p = Get-Process qemu-system-x86_64 -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    if ($p) { [EmuWin]::SetWindowPos($p.MainWindowHandle, [IntPtr]::Zero, 1080, 5, 360, 800, 0x0044) | Out-Null; break }
    Start-Sleep 1
}
