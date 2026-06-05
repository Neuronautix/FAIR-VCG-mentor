import ArticleIcon from '@mui/icons-material/Article'
import CloudUploadIcon from '@mui/icons-material/CloudUpload'
import DescriptionIcon from '@mui/icons-material/Description'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  Grid,
  Stack,
  TextField,
  Typography,
  LinearProgress,
} from '@mui/material'
import type { AxiosError } from 'axios'
import { useCallback, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import ScienceIcon from '@mui/icons-material/Science'
import {
  buildMetadataPatch,
  extractPaperMetadataStream,
  importFreeText,
  saveMetadata,
  startAssessmentOnly,
  startDemoSession,
  uploadCSV,
} from '../api/client'
import type { PaperExtraction } from '../store/useStore'
import { useStore } from '../store/useStore'

function CSVDropZone({
  onFile,
  loading,
}: {
  onFile: (f: File) => void
  loading: boolean
}) {
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragging(false)
      const f = e.dataTransfer.files[0]
      if (f) onFile(f)
    },
    [onFile],
  )

  return (
    <Box
      onDragOver={(e) => {
        e.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      onClick={() => !loading && inputRef.current?.click()}
      sx={{
        border: '2px dashed',
        borderColor: dragging ? 'primary.main' : 'grey.300',
        borderRadius: 3,
        p: 4,
        textAlign: 'center',
        cursor: loading ? 'default' : 'pointer',
        bgcolor: dragging ? 'primary.50' : 'grey.50',
        transition: 'all 0.15s',
        '&:hover': !loading ? { borderColor: 'primary.light', bgcolor: 'primary.50' } : {},
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".csv,.xlsx,.xls"
        style={{ display: 'none' }}
        onChange={(e) => {
          const f = e.target.files?.[0]
          if (f) onFile(f)
        }}
      />
      {loading ? (
        <Box>
          <CircularProgress size={36} sx={{ mb: 1 }} />
          <Typography variant="body2" color="text.secondary">
            Analysing dataset…
          </Typography>
        </Box>
      ) : (
        <>
          <CloudUploadIcon sx={{ fontSize: 44, color: 'grey.400', mb: 1 }} />
          <Typography variant="subtitle1" fontWeight={600}>
            Drop CSV or Excel file here
          </Typography>
          <Typography variant="body2" color="text.secondary">
            or click to browse
          </Typography>
        </>
      )}
    </Box>
  )
}

function PDFDropZone({
  label,
  sublabel,
  onFile,
  loading,
  done,
}: {
  label: string
  sublabel: string
  onFile: (f: File) => void
  loading: boolean
  done: boolean
}) {
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragging(false)
      const f = e.dataTransfer.files[0]
      if (f && f.type === 'application/pdf') onFile(f)
    },
    [onFile],
  )

  return (
    <Box
      onDragOver={(e) => {
        e.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      onClick={() => !loading && !done && inputRef.current?.click()}
      sx={{
        border: '2px dashed',
        borderColor: done ? 'success.main' : dragging ? 'primary.main' : 'grey.300',
        borderRadius: 2,
        p: 3,
        textAlign: 'center',
        cursor: loading || done ? 'default' : 'pointer',
        bgcolor: done ? 'success.50' : dragging ? 'primary.50' : 'grey.50',
        transition: 'all 0.15s',
        '&:hover': !loading && !done ? { borderColor: 'primary.light', bgcolor: 'primary.50' } : {},
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".pdf"
        style={{ display: 'none' }}
        onChange={(e) => {
          const f = e.target.files?.[0]
          if (f) onFile(f)
        }}
      />
      {loading ? (
        <Box>
          <CircularProgress size={28} sx={{ mb: 0.5 }} />
          <Typography variant="caption" color="text.secondary" display="block">
            Extracting…
          </Typography>
        </Box>
      ) : done ? (
        <Stack direction="row" alignItems="center" justifyContent="center" spacing={1}>
          <CheckCircleIcon color="success" fontSize="small" />
          <Typography variant="body2" color="success.main" fontWeight={600}>
            Extracted
          </Typography>
        </Stack>
      ) : (
        <>
          <ArticleIcon sx={{ fontSize: 36, color: 'grey.400', mb: 0.5 }} />
          <Typography variant="subtitle2" fontWeight={600}>
            {label}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {sublabel}
          </Typography>
        </>
      )}
    </Box>
  )
}

export default function ImportPage() {
  const navigate = useNavigate()
  const { setUploadResult, reset, setPaperExtraction, setAssessmentOnly, datasetId, aiConfigured } =
    useStore()

  // CSV state
  const [csvLoading, setCsvLoading] = useState(false)
  const [csvError, setCsvError] = useState<string | null>(null)
  const [csvDone, setCsvDone] = useState(false)

  // Paper PDF state
  const [paperLoading, setPaperLoading] = useState(false)
  const [paperStatus, setPaperStatus] = useState<string>('')
  const [paperError, setPaperError] = useState<string | null>(null)
  const [paperDone, setPaperDone] = useState(false)
  const [paperResult, setPaperResult] = useState<PaperExtraction | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  // Protocol PDF state
  const [protocolLoading, setProtocolLoading] = useState(false)
  const [protocolStatus, setProtocolStatus] = useState<string>('')
  const [protocolError, setProtocolError] = useState<string | null>(null)
  const [protocolDone, setProtocolDone] = useState(false)

  // Free text state
  const [freeText, setFreeText] = useState('')
  const [freeTextLoading, setFreeTextLoading] = useState(false)
  const [freeTextError, setFreeTextError] = useState<string | null>(null)
  const [freeTextDone, setFreeTextDone] = useState(false)

  // Skip / assessment-only state
  const [skipLoading, setSkipLoading] = useState(false)

  // Demo preload state
  const [demoLoading, setDemoLoading] = useState(false)
  const [demoError, setDemoError] = useState<string | null>(null)

  const handleCSV = useCallback(
    async (file: File) => {
      setCsvError(null)
      setCsvLoading(true)
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
            templateId: result.template_id ?? null,
            templateCandidates: result.template_candidates ?? [],
          },
        )
        setAssessmentOnly(false)

        // Apply any paper extraction that was done before the CSV upload
        if (paperResult) {
          const patch = buildMetadataPatch(paperResult)
          try {
            await saveMetadata(result.dataset_id, patch)
          } catch {
            // non-fatal
          }
        }
        setCsvDone(true)
        navigate('/overview')
      } catch (e: unknown) {
        const axiosErr = e as AxiosError<{ detail: string }>
        const msg =
          axiosErr.response?.data?.detail ??
          (e instanceof Error ? e.message : 'Upload failed')
        setCsvError(msg)
      } finally {
        setCsvLoading(false)
      }
    },
    [navigate, reset, setUploadResult, setPaperExtraction, paperResult, setAssessmentOnly],
  )

  const handlePaperPDF = useCallback(async (file: File) => {
    abortRef.current?.abort()
    abortRef.current = new AbortController()
    setPaperError(null)
    setPaperLoading(true)
    setPaperStatus('Starting extraction…')
    try {
      await extractPaperMetadataStream(
        file,
        (msg) => setPaperStatus(msg),
        (data) => {
          const extraction = data as PaperExtraction
          setPaperResult(extraction)
          setPaperExtraction(extraction)
          setPaperLoading(false)
          setPaperDone(true)
        },
        (msg) => {
          setPaperError(msg)
          setPaperLoading(false)
        },
        abortRef.current.signal,
      )
    } catch (err: any) {
      if (err?.name === 'AbortError') return
      setPaperError(err?.message ?? 'Extraction failed.')
      setPaperLoading(false)
    }
  }, [setPaperExtraction])

  const handleProtocolPDF = useCallback(async (file: File) => {
    abortRef.current?.abort()
    abortRef.current = new AbortController()
    setProtocolError(null)
    setProtocolLoading(true)
    setProtocolStatus('Starting extraction…')
    try {
      await extractPaperMetadataStream(
        file,
        (msg) => setProtocolStatus(msg),
        (data) => {
          const extraction = data as PaperExtraction
          setPaperExtraction(extraction)
          setProtocolLoading(false)
          setProtocolDone(true)
        },
        (msg) => {
          setProtocolError(msg)
          setProtocolLoading(false)
        },
        abortRef.current.signal,
      )
    } catch (err: any) {
      if (err?.name === 'AbortError') return
      setProtocolError(err?.message ?? 'Extraction failed.')
      setProtocolLoading(false)
    }
  }, [setPaperExtraction])

  const handleFreeTextAnalyse = async () => {
    if (!freeText.trim()) return
    setFreeTextError(null)
    setFreeTextLoading(true)
    try {
      const result = await importFreeText(freeText)
      setPaperExtraction(result as PaperExtraction)
      setFreeTextDone(true)
    } catch (err: any) {
      const msg =
        err?.response?.data?.detail ??
        err?.message ??
        'Analysis failed.'
      setFreeTextError(msg)
    } finally {
      setFreeTextLoading(false)
    }
  }

  const handleSkip = async () => {
    setSkipLoading(true)
    try {
      const result = await startAssessmentOnly()
      setUploadResult(
        result.dataset_id,
        {
          filename: 'No dataset',
          n_rows: 0,
          n_columns: 0,
          delimiter: '',
          encoding: '',
          has_header: true,
          empty_columns: [],
          duplicate_columns: [],
          malformed_rows: [],
        },
        [],
        {
          table_shape: 'assessment_only',
          row_represents: 'n/a',
          primary_entity: 'n/a',
          secondary_entity: null,
          detected_identifiers: [],
          detected_measurements: [],
          detected_categoricals: [],
          detected_time_vars: [],
        },
        [],
        {},
      )
      setAssessmentOnly(true)
      navigate('/templates')
    } catch (err: any) {
      // navigate anyway — templates page works without a dataset
      setAssessmentOnly(true)
      navigate('/templates')
    } finally {
      setSkipLoading(false)
    }
  }

  const handleLoadDemo = async () => {
    setDemoLoading(true)
    setDemoError(null)
    reset()
    try {
      const result = await startDemoSession()
      setUploadResult(
        result.dataset_id,
        result.import_info,
        result.columns,
        result.table_structure,
        result.issues,
        {
          lowConfidenceColumns: result.low_confidence_columns ?? [],
          templateApplied: result.template_applied ?? 0,
          templateId: result.template_id ?? null,
          templateCandidates: result.template_candidates ?? [],
        },
      )
      setAssessmentOnly(false)
      navigate('/template-fill')
    } catch (err: any) {
      const msg =
        err?.response?.data?.detail ??
        (err?.response?.status === 500
          ? 'Demo load failed. In dev mode, make sure the FastAPI backend is running on http://localhost:8000.'
          : err?.message) ??
        'Demo load failed.'
      setDemoError(msg)
    } finally {
      setDemoLoading(false)
    }
  }

  return (
    <Box sx={{ maxWidth: 960, mx: 'auto' }}>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h5" gutterBottom>
          Import
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Upload your research documents to assess ARRIVE 2.0 reporting completeness and PREPARE
          study planning readiness — with or without a dataset.
        </Typography>
      </Box>

      {/* Demo preload banner */}
      <Card
        sx={{
          mb: 3,
          background: 'linear-gradient(135deg, #e3f2fd 0%, #f3e5f5 100%)',
          border: '1px solid',
          borderColor: 'primary.light',
        }}
      >
        <CardContent sx={{ display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
          <ScienceIcon color="primary" sx={{ fontSize: 36 }} />
          <Box sx={{ flex: 1, minWidth: 200 }}>
            <Typography variant="subtitle1" fontWeight={700}>
              Try the demo — no API key needed
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Loads a pre-filled example from{' '}
              <strong>Huzard et al. (2025), Translational Psychiatry</strong> — mechanical itch
              hypersensitivity in a Shank3 mouse model of autism. All ARRIVE 2.0 and PREPARE fields
              are extracted and ready to explore.
            </Typography>
          </Box>
          <Stack spacing={1} alignItems="flex-end">
            <Button
              variant="contained"
              color="primary"
              onClick={handleLoadDemo}
              disabled={demoLoading}
              startIcon={demoLoading ? <CircularProgress size={16} color="inherit" /> : <ScienceIcon />}
              sx={{ whiteSpace: 'nowrap' }}
            >
              {demoLoading ? 'Loading demo…' : 'Load example dataset'}
            </Button>
            {demoError && (
              <Alert severity="error" onClose={() => setDemoError(null)} sx={{ py: 0.5 }}>
                {demoError}
              </Alert>
            )}
          </Stack>
        </CardContent>
      </Card>

      <Grid container spacing={3}>
        {/* Panel 1: Research Documents */}
        <Grid item xs={12} md={7}>
          <Card sx={{ height: '100%' }}>
            <CardContent>
              <Stack direction="row" alignItems="center" spacing={1} mb={2}>
                <ArticleIcon color="primary" />
                <Typography variant="h6">Research Documents</Typography>
                <Chip label="Always available" size="small" color="primary" variant="outlined" />
              </Stack>

              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Upload publications or protocols to extract ARRIVE 2.0 and PREPARE metadata. No
                dataset required.
              </Typography>

              <Stack spacing={2}>
                {/* Published paper PDF */}
                <Box>
                  <Typography variant="subtitle2" fontWeight={600} sx={{ mb: 0.75 }}>
                    Published Paper (PDF)
                  </Typography>
                  <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
                    Extract ARRIVE 2.0 reporting fields and study metadata from a published paper or
                    preprint.
                  </Typography>
                  <PDFDropZone
                    label="Drop paper PDF here"
                    sublabel="or click to browse"
                    onFile={handlePaperPDF}
                    loading={paperLoading}
                    done={paperDone}
                  />
                  {paperLoading && (
                    <Box sx={{ mt: 1 }}>
                      <LinearProgress />
                      <Typography variant="caption" color="text.secondary">
                        {paperStatus}
                      </Typography>
                    </Box>
                  )}
                  {paperError && (
                    <Alert severity="error" sx={{ mt: 1 }} onClose={() => setPaperError(null)}>
                      {paperError}
                    </Alert>
                  )}
                  {paperDone && (
                    <Alert severity="success" sx={{ mt: 1 }}>
                      Paper metadata extracted. ARRIVE 2.0 fields are ready to apply.
                    </Alert>
                  )}
                </Box>

                <Divider />

                {/* Protocol / study plan PDF */}
                <Box>
                  <Typography variant="subtitle2" fontWeight={600} sx={{ mb: 0.75 }}>
                    Protocol / Study Plan (PDF)
                  </Typography>
                  <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
                    Assess PREPARE planning readiness from a protocol document or study plan.
                  </Typography>
                  <PDFDropZone
                    label="Drop protocol PDF here"
                    sublabel="or click to browse"
                    onFile={handleProtocolPDF}
                    loading={protocolLoading}
                    done={protocolDone}
                  />
                  {protocolLoading && (
                    <Box sx={{ mt: 1 }}>
                      <LinearProgress />
                      <Typography variant="caption" color="text.secondary">
                        {protocolStatus}
                      </Typography>
                    </Box>
                  )}
                  {protocolError && (
                    <Alert severity="error" sx={{ mt: 1 }} onClose={() => setProtocolError(null)}>
                      {protocolError}
                    </Alert>
                  )}
                  {protocolDone && (
                    <Alert severity="success" sx={{ mt: 1 }}>
                      Protocol metadata extracted. PREPARE fields are ready to apply.
                    </Alert>
                  )}
                </Box>

                <Divider />

                {/* Free text */}
                <Box>
                  <Typography variant="subtitle2" fontWeight={600} sx={{ mb: 0.75 }}>
                    Protocol Notes (Free Text)
                  </Typography>
                  <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
                    Paste protocol notes, study plan text, or any relevant text to extract PREPARE
                    and ARRIVE metadata with AI.
                  </Typography>
                  <TextField
                    multiline
                    minRows={4}
                    maxRows={10}
                    fullWidth
                    size="small"
                    placeholder="Paste protocol notes, study plan, or any relevant text here…"
                    value={freeText}
                    onChange={(e) => setFreeText(e.target.value)}
                    disabled={freeTextLoading}
                    inputProps={{ maxLength: 20000 }}
                  />
                  {!aiConfigured && (
                    <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
                      AI analysis requires an OpenAI key. Configure it in Settings.
                    </Typography>
                  )}
                  {freeTextError && (
                    <Alert severity="error" sx={{ mt: 1 }} onClose={() => setFreeTextError(null)}>
                      {freeTextError}
                    </Alert>
                  )}
                  {freeTextDone && (
                    <Alert severity="success" sx={{ mt: 1 }}>
                      Text analysed. Metadata extracted and ready to apply.
                    </Alert>
                  )}
                  <Box sx={{ mt: 1, display: 'flex', justifyContent: 'flex-end' }}>
                    <Button
                      variant="contained"
                      size="small"
                      onClick={handleFreeTextAnalyse}
                      disabled={freeTextLoading || !freeText.trim() || !aiConfigured}
                      startIcon={
                        freeTextLoading ? <CircularProgress size={14} color="inherit" /> : <DescriptionIcon />
                      }
                    >
                      {freeTextLoading ? 'Analysing…' : 'Analyse with AI'}
                    </Button>
                  </Box>
                </Box>
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        {/* Panel 2: Dataset (optional) */}
        <Grid item xs={12} md={5}>
          <Card sx={{ height: '100%' }}>
            <CardContent>
              <Stack direction="row" alignItems="center" spacing={1} mb={2}>
                <CloudUploadIcon color="action" />
                <Typography variant="h6">Dataset</Typography>
                <Chip label="Optional" size="small" variant="outlined" />
              </Stack>

              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Upload your results data for a full FAIR assessment. Not required for ARRIVE/PREPARE
                assessment only.
              </Typography>

              <CSVDropZone onFile={handleCSV} loading={csvLoading} />

              {csvError && (
                <Alert severity="error" sx={{ mt: 2 }} onClose={() => setCsvError(null)}>
                  {csvError}
                </Alert>
              )}

              {csvDone && (
                <Alert severity="success" sx={{ mt: 2 }}>
                  Dataset uploaded. Redirecting to overview…
                </Alert>
              )}

              <Divider sx={{ my: 2 }}>
                <Typography variant="caption" color="text.secondary">
                  or
                </Typography>
              </Divider>

              <Button
                fullWidth
                variant="outlined"
                color="secondary"
                onClick={handleSkip}
                disabled={skipLoading}
                startIcon={skipLoading ? <CircularProgress size={16} /> : undefined}
              >
                {skipLoading ? 'Starting session…' : 'Skip — Assess ARRIVE/PREPARE only'}
              </Button>
              <Typography variant="caption" color="text.secondary" sx={{ mt: 0.75, display: 'block', textAlign: 'center' }}>
                Opens Templates page in ARRIVE/PREPARE assessment mode
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Info banner */}
      <Box sx={{ mt: 3, p: 2.5, background: '#f0f4ff', borderRadius: 2 }}>
        <Typography variant="subtitle2" fontWeight={700} gutterBottom>
          What this tool assesses
        </Typography>
        <Grid container spacing={2}>
          <Grid item xs={12} sm={4}>
            <Typography variant="body2" color="text.secondary">
              <strong>ARRIVE 2.0</strong> — Did you report everything needed to evaluate your
              published study?
            </Typography>
          </Grid>
          <Grid item xs={12} sm={4}>
            <Typography variant="body2" color="text.secondary">
              <strong>PREPARE</strong> — Did you plan everything needed before running your
              experiment?
            </Typography>
          </Grid>
          <Grid item xs={12} sm={4}>
            <Typography variant="body2" color="text.secondary">
              <strong>FAIR</strong> — Is your dataset Findable, Accessible, Interoperable, and
              Reusable? (requires dataset upload)
            </Typography>
          </Grid>
        </Grid>
        <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
          These are readiness assessments, not legal or regulatory certifications.
        </Typography>
      </Box>
    </Box>
  )
}
