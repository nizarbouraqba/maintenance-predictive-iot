param([string]$Destination)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

function Invoke-DockerChecked {
    param([string[]]$Arguments)
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Docker a échoué : $($Arguments -join ' ')" }
}

Invoke-DockerChecked -Arguments @('info', '--format', '{{.OSType}}')
if ([string]::IsNullOrWhiteSpace($Destination)) {
    $Destination = Join-Path (Split-Path -Parent $PSScriptRoot) ('export-docker-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
}
$Destination = [IO.Path]::GetFullPath($Destination)
if (Test-Path -LiteralPath $Destination) { throw "Choisir un nouveau dossier : $Destination existe déjà." }
$projectPrefix = $PSScriptRoot.TrimEnd('\','/') + [IO.Path]::DirectorySeparatorChar
if ($Destination -eq $PSScriptRoot -or $Destination.StartsWith($projectPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Choisir une destination en dehors du dossier source du projet.'
}

Invoke-DockerChecked -Arguments @('build', '--tag', 'pdm-project:1.0', '.')
$imageNames = @(& docker compose -f docker-compose.portable.yml --profile full --profile demo config --images)
if ($LASTEXITCODE -ne 0) { throw 'Impossible de lire la liste des images.' }
$imageNames = @($imageNames | Sort-Object -Unique)
foreach ($imageName in $imageNames) {
    & docker image inspect $imageName --format '{{.Id}}' *> $null
    if ($LASTEXITCODE -ne 0) {
        Invoke-DockerChecked -Arguments @('pull', $imageName)
    }
}

New-Item -ItemType Directory -Path $Destination | Out-Null
foreach ($directory in @('mosquitto','grafana','node_red','thingsboard','data','models','reports','notebooks','pdm','tests','docs')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $directory) -Destination $Destination -Recurse
}
Copy-Item -LiteralPath 'docker-compose.portable.yml' -Destination (Join-Path $Destination 'docker-compose.yml')
Copy-Item -LiteralPath '.env.example' -Destination $Destination
Copy-Item -LiteralPath 'GUIDE-IMAGE-DOCKER.md' -Destination (Join-Path $Destination 'README.md')

$archive = Join-Path $Destination 'projet-11-images.tar'
Invoke-DockerChecked -Arguments (@('image', 'save', '--output', $archive) + $imageNames)
$hash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash
[IO.File]::WriteAllText((Join-Path $Destination 'projet-11-images.sha256'), "$hash  projet-11-images.tar`n")
$metadata = & docker image inspect @imageNames --format '{{.RepoTags}} | {{.Id}} | {{.Os}}/{{.Architecture}}'
if ($LASTEXITCODE -ne 0) { throw 'Impossible de vérifier les images exportées.' }
$metadata | Set-Content -LiteralPath (Join-Path $Destination 'images-manifest.txt') -Encoding utf8
Write-Host "Export terminé : $Destination"
Write-Host 'Copier tout ce dossier sur la machine cible, puis suivre README.md.'
Write-Host 'Les volumes, historiques locaux, tokens et paramètres .env personnels ne sont pas exportés.'
