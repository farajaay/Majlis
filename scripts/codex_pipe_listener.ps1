param(
  [string]$PipeName = "majlis-codex",
  [string]$InboxDir = ".majlis-pipe-inbox",
  [string]$LogPath = ".majlis-pipe-listener.log",
  [switch]$OpenCodex
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
New-Item -ItemType Directory -Force -Path $InboxDir | Out-Null

function Write-Log {
  param([string]$Message)
  $line = "$(Get-Date -Format o) $Message"
  Add-Content -Path $LogPath -Value $line -Encoding utf8
}

function Save-Packet {
  param([string]$Line)

  $packet = $Line | ConvertFrom-Json
  $room = if ($packet.room) { [string]$packet.room } else { "room" }
  $seat = if ($packet.seat) { [string]$packet.seat } else { "seat" }
  $seq = if ($packet.seq) { [string]$packet.seq } else { "unknown" }
  $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
  $safeRoom = $room -replace "[^A-Za-z0-9_.-]", "_"
  $safeSeat = $seat -replace "[^A-Za-z0-9_.-]", "_"
  $base = Join-Path $InboxDir "$stamp-$safeRoom-$safeSeat-$seq"

  Set-Content -Path "$base.json" -Value $Line -Encoding utf8
  if ($packet.prompt) {
    Set-Content -Path "$base.md" -Value ([string]$packet.prompt) -Encoding utf8
    try {
      Set-Clipboard -Value ([string]$packet.prompt)
    } catch {
      Write-Log "clipboard failed room=$room seat=$seat seq=$seq error=$($_.Exception.Message)"
    }
  }

  if ($OpenCodex) {
    try {
      Start-Process "shell:AppsFolder\OpenAI.Codex_2p2nqsd0c76g0!App" | Out-Null
    } catch {
      Write-Log "open codex failed room=$room seat=$seat seq=$seq error=$($_.Exception.Message)"
    }
  }

  Write-Log "accepted room=$room seat=$seat seq=$seq path=$base"
}

Write-Log "starting pipe=\\.\pipe\$PipeName inbox=$InboxDir open_codex=$OpenCodex"

while ($true) {
  $server = $null
  $reader = $null
  try {
    $server = [System.IO.Pipes.NamedPipeServerStream]::new(
      $PipeName,
      [System.IO.Pipes.PipeDirection]::In,
      1,
      [System.IO.Pipes.PipeTransmissionMode]::Byte,
      [System.IO.Pipes.PipeOptions]::None
    )
    $server.WaitForConnection()
    $reader = [System.IO.StreamReader]::new($server, [System.Text.UTF8Encoding]::new($false))
    $line = $reader.ReadLine()
    if ($line) {
      Save-Packet $line
    }
  } catch {
    Write-Log "listener error=$($_.Exception.Message)"
    Start-Sleep -Seconds 1
  } finally {
    if ($reader) { $reader.Dispose() }
    if ($server) { $server.Dispose() }
  }
}
