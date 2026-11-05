# Run from the repo root. Starts a local Bifrost gateway using ./bifrost/config.json.
# Secrets come from .env (never stored in the config file).
Get-Content ".env" | ForEach-Object {
    if ($_ -match '^([A-Z_]+)=(.*)$') { Set-Item "env:$($Matches[1])" $Matches[2] }
}
npx -y @maximhq/bifrost -app-dir ./bifrost -host 127.0.0.1
