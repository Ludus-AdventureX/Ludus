# Ludus daily DB backup (interlude B).
# Register as a Windows scheduled task, e.g.:
#   schtasks /Create /SC DAILY /ST 03:30 /TN LudusDbBackup /TR "powershell -NoProfile -File <this file>"
# Keeps the last 14 dumps; requires the prototype stack's db container to be up.

$ErrorActionPreference = "Stop"
$backupDir = Join-Path $PSScriptRoot "..\backups"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$target = Join-Path $backupDir "decision_lab-$stamp.dump"

docker exec decision-lab-prototype-db-1 pg_dump -U decision_lab -d decision_lab -F c -f /tmp/backup.dump
if ($LASTEXITCODE -ne 0) { throw "pg_dump failed" }
docker cp decision-lab-prototype-db-1:/tmp/backup.dump $target
docker exec decision-lab-prototype-db-1 rm -f /tmp/backup.dump

# Retention: newest 14 stay.
Get-ChildItem $backupDir -Filter "decision_lab-*.dump" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip 14 |
    Remove-Item -Force

Write-Output "backup OK -> $target"
