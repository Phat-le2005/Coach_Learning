$PdfStorageRoot = if ($env:PDFMETA_STORAGE_ROOT) {
    $env:PDFMETA_STORAGE_ROOT
} else {
    'C:\CoachLearningPdf'
}

$PdfStorageRoot = [IO.Path]::GetFullPath($PdfStorageRoot)
$PdfRuntimeRoot = Join-Path $PdfStorageRoot 'pdf-pipeline-runtime'
$PdfJobsRoot = Join-Path $PdfStorageRoot 'pdf-jobs'
$PdfQueuesRoot = Join-Path $PdfStorageRoot 'pdf-queues'

$env:PDFMETA_STORAGE_ROOT = $PdfStorageRoot
$env:PDFMETA_RUNTIME_ROOT = $PdfRuntimeRoot

function Get-PdfFileSha256 {
    param([Parameter(Mandatory=$true)][string]$LiteralPath)
    # Python-launched Windows PowerShell may lack the Get-FileHash function in
    # its module search path. Hash through .NET without changing global modules.
    $pdfHashStream=[IO.File]::OpenRead((Resolve-Path -LiteralPath $LiteralPath).ProviderPath)
    $pdfHasher=[Security.Cryptography.SHA256]::Create()
    try { [BitConverter]::ToString($pdfHasher.ComputeHash($pdfHashStream)).Replace('-','').ToLowerInvariant() }
    finally { $pdfHasher.Dispose();$pdfHashStream.Dispose() }
}
