import CloudUploadIcon from '@mui/icons-material/CloudUpload'
import { Alert, Box, Button, CircularProgress, Paper, Snackbar, Typography } from '@mui/material'
import type { AxiosError } from 'axios'
import { useCallback, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { buildMetadataPatch, saveMetadata, uploadCSV } from '../api/client'
import { useStore } from '../store/useStore'

export default function UploadPage() {
  const navigate = useNavigate()
  const { setUploadResult, reset, paperExtraction } = useStore()
  const [dragging, setDragging] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [paperSnackbar, setPaperSnackbar] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleFile = useCallback(
    async (file: File) => {
      if (!file.name.toLowerCase().endsWith('.csv') && !file.type.includes('csv') && !file.type.includes('text')) {
        setError('Please upload a CSV file.')
        return
      }
      setError(null)
      setLoading(true)
      reset()
      try {
        const result = await uploadCSV(file)
        setUploadResult(
          result.dataset_id,
          result.import_info,
          result.columns,
          result.table_structure,
          result.issues,
          {
            lowConfidenceColumns: result.low_confidence_columns ?? [],
            templateApplied: result.template_applied ?? 0,
          }
        )

        if (paperExtraction) {
          const patch = buildMetadataPatch(paperExtraction)
          try {
            await saveMetadata(result.dataset_id, patch)
            setPaperSnackbar(
              `Pre-filled ${Object.keys(patch).length} metadata field(s) from "${paperExtraction._filename}"`
            )
          } catch {
            // non-fatal: proceed to overview even if pre-fill fails
          }
        }

        navigate('/overview')
      } catch (e: unknown) {
        const axiosErr = e as AxiosError<{ detail: string }>
        const msg = axiosErr.response?.data?.detail ?? (e instanceof Error ? e.message : 'Upload failed')
        setError(msg)
      } finally {
        setLoading(false)
      }
    },
    [navigate, reset, setUploadResult, paperExtraction]
  )

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragging(false)
      const file = e.dataTransfer.files[0]
      if (file) handleFile(file)
    },
    [handleFile]
  )

  return (
    <Box sx={{ maxWidth: 680, mx: 'auto', mt: 6 }}>
      <Typography variant="h4" gutterBottom>
        FAIR CSV Mentor
      </Typography>
      <Typography variant="body1" color="text.secondary" sx={{ mb: 4 }}>
        Upload a CSV file to receive a FAIR-readiness assessment. The tool will analyse your data
        structure, detect metadata gaps, and help you export a more machine-actionable version of
        your dataset.
      </Typography>

      <Paper
        variant="outlined"
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        sx={{
          border: `2px dashed ${dragging ? '#1976d2' : '#bdbdbd'}`,
          background: dragging ? 'rgba(25,118,210,0.05)' : 'white',
          borderRadius: 3,
          p: 6,
          textAlign: 'center',
          cursor: 'pointer',
          transition: 'all 0.2s',
        }}
        onClick={() => inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".csv,text/csv"
          style={{ display: 'none' }}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f) }}
        />
        {loading ? (
          <CircularProgress size={48} />
        ) : (
          <>
            <CloudUploadIcon sx={{ fontSize: 56, color: '#bdbdbd', mb: 2 }} />
            <Typography variant="h6" fontWeight={600}>
              Drop your CSV here
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
              or click to browse
            </Typography>
          </>
        )}
      </Paper>

      {error && (
        <Alert severity="error" sx={{ mt: 2 }}>
          {error}
        </Alert>
      )}

      <Snackbar
        open={paperSnackbar !== null}
        autoHideDuration={5000}
        onClose={() => setPaperSnackbar(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert severity="info" onClose={() => setPaperSnackbar(null)}>
          {paperSnackbar}
        </Alert>
      </Snackbar>

      <Button
        variant="contained"
        size="large"
        startIcon={<CloudUploadIcon />}
        sx={{ mt: 3, width: '100%' }}
        onClick={() => inputRef.current?.click()}
        disabled={loading}
      >
        {loading ? 'Analysing…' : 'Choose CSV file'}
      </Button>

      <Box sx={{ mt: 5, p: 2.5, background: '#f0f4ff', borderRadius: 2 }}>
        <Typography variant="subtitle2" fontWeight={700} gutterBottom>
          What this tool assesses
        </Typography>
        <Typography variant="body2" color="text.secondary">
          <strong>Findable</strong> — Can the dataset be discovered with a title, description, and identifier?
          <br />
          <strong>Accessible</strong> — Is there a license and contact information?
          <br />
          <strong>Interoperable</strong> — Are column names, units, and vocabularies machine-readable?
          <br />
          <strong>Reusable</strong> — Is there a data dictionary, provenance, and protocol reference?
        </Typography>
        <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
          This is a FAIR-readiness assessment, not a legal or regulatory certification.
        </Typography>
      </Box>
    </Box>
  )
}
