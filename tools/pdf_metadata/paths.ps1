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
