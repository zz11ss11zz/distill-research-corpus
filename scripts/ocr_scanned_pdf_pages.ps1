param(
    [string]$WorkspaceRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$DocumentsJson = 'outputs/json/knowledge_distillation/ocr_targets.json',
    [string]$OutputJson = 'outputs/json/knowledge_distillation/ocr_pages.json',
    [int]$Dpi = 200,
    [int]$Limit = 0
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Storage.Streams.IRandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrResult, Windows.Foundation, ContentType = WindowsRuntime]

function Await-WinRt($Operation, [Type]$ResultType) {
    $asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() |
        Where-Object {
            $_.Name -eq 'AsTask' -and
            $_.IsGenericMethod -and
            $_.GetParameters().Count -eq 1 -and
            $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
        } |
        Select-Object -First 1
    $task = $asTask.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
    $task.Wait()
    return $task.Result
}

function Get-LongPath([string]$Path) {
    $absolute = [System.IO.Path]::GetFullPath($Path)
    if ($absolute.StartsWith('\\')) {
        return '\\?\UNC\' + $absolute.Substring(2)
    }
    return '\\?\' + $absolute
}

function Invoke-ImageOcr([string]$ImagePath, $Engine) {
    $file = Await-WinRt ([Windows.Storage.StorageFile]::GetFileFromPathAsync($ImagePath)) ([Windows.Storage.StorageFile])
    $stream = Await-WinRt ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    try {
        $decoder = Await-WinRt ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
        $bitmap = Await-WinRt ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
        try {
            $result = Await-WinRt ($Engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
            return $result.Text
        } finally {
            if ($bitmap -is [System.IDisposable]) { $bitmap.Dispose() }
        }
    } finally {
        if ($stream -is [System.IDisposable]) { $stream.Dispose() }
    }
}

function Save-Json($Payload, [string]$Path) {
    $json = $Payload | ConvertTo-Json -Depth 12
    [System.IO.File]::WriteAllText($Path, $json + "`n", [System.Text.UTF8Encoding]::new($false))
}

$documentsPath = Join-Path $WorkspaceRoot $DocumentsJson
$outputPath = Join-Path $WorkspaceRoot $OutputJson
$outputDir = Split-Path -Parent $outputPath
[System.IO.Directory]::CreateDirectory($outputDir) | Out-Null
$tempRoot = Join-Path $WorkspaceRoot 'tmp\pdfs\knowledge_distillation_ocr'
[System.IO.Directory]::CreateDirectory($tempRoot) | Out-Null

$language = [Windows.Globalization.Language]::new('zh-Hans-CN')
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($language)
if ($null -eq $engine) { throw 'Unable to create Windows OCR engine for zh-Hans-CN.' }

$documents = Get-Content -LiteralPath $documentsPath -Raw -Encoding UTF8 | ConvertFrom-Json
$targets = @($documents | Where-Object {
    $_.extraction.text_coverage_status -like 'ocr*' -or $_.distillation_status -like 'unreadable*'
})
if ($Limit -gt 0) { $targets = @($targets | Select-Object -First $Limit) }

if (Test-Path -LiteralPath $outputPath) {
    $payload = Get-Content -LiteralPath $outputPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $payload.documents = @($payload.documents | Where-Object {
        @($_.pages | Where-Object {
            -not [string]::IsNullOrWhiteSpace([string]$_.text) -and [string]::IsNullOrWhiteSpace([string]$_.error)
        }).Count -gt 0
    })
} else {
    $payload = [ordered]@{
        schema_version = '1.0.0'
        generated_at = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
        language = 'zh-Hans-CN'
        dpi = $Dpi
        documents = @()
    }
}
$completed = @{}
foreach ($item in @($payload.documents)) { $completed[$item.sha256] = $true }

$pdftoppmCommand = (Get-Command pdftoppm -ErrorAction Stop).Source
$pdftoppm = [System.IO.Path]::GetFullPath((Join-Path (Split-Path -Parent $pdftoppmCommand) '..\..\native\poppler\Library\bin\pdftoppm.exe'))
if (-not (Test-Path -LiteralPath $pdftoppm -PathType Leaf)) { $pdftoppm = $pdftoppmCommand }
$processedDocuments = 0
$processedPages = 0
foreach ($document in $targets) {
    if ($completed.ContainsKey($document.sha256)) {
        Write-Host "OCR skip existing: $($document.path)"
        continue
    }
    $sourcePath = Join-Path $WorkspaceRoot ($document.path.Replace('/', '\'))
    $renderSourcePath = if ($sourcePath.Length -ge 240) { Get-LongPath $sourcePath } else { $sourcePath }
    $docTemp = Join-Path $tempRoot $document.source_id
    [System.IO.Directory]::CreateDirectory($docTemp) | Out-Null
    $pageResults = New-Object System.Collections.Generic.List[object]
    for ($page = 1; $page -le [int]$document.extraction.page_count; $page++) {
        $prefix = Join-Path $docTemp ('page-{0:D4}' -f $page)
        $imagePath = $prefix + '.png'
        & $pdftoppm -f $page -l $page -r $Dpi -singlefile -png $renderSourcePath $prefix
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $imagePath)) {
            $pageResults.Add([ordered]@{ page = $page; text = ''; error = 'render_failed' })
            continue
        }
        try {
            $text = Invoke-ImageOcr ([System.IO.Path]::GetFullPath($imagePath)) $engine
            $pageResults.Add([ordered]@{ page = $page; text = $text; error = $null })
        } catch {
            $pageResults.Add([ordered]@{ page = $page; text = ''; error = $_.Exception.Message })
        } finally {
            Remove-Item -LiteralPath $imagePath -Force -ErrorAction SilentlyContinue
        }
        $processedPages++
        if (($processedPages % 10) -eq 0) { Write-Host "OCR pages processed: $processedPages" }
    }
    [object[]]$pageArray = @($pageResults | ForEach-Object { $_ })
    $entry = [ordered]@{
        source_id = $document.source_id
        path = $document.path
        sha256 = $document.sha256
        page_count = [int]$document.extraction.page_count
        pages = $pageArray
    }
    $payload.documents = @($payload.documents) + @($entry)
    $payload.generated_at = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
    Save-Json $payload $outputPath
    $completed[$document.sha256] = $true
    $processedDocuments++
    Remove-Item -LiteralPath $docTemp -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "OCR document complete: $($document.path)"
}

Write-Host "OCR complete. Documents processed: $processedDocuments; pages processed: $processedPages; output: $outputPath"
