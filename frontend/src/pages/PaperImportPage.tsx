import { useCallback, useEffect, useRef, useState } from 'react'
import ArticleIcon from '@mui/icons-material/Article'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import DownloadIcon from '@mui/icons-material/Download'
import ErrorIcon from '@mui/icons-material/Error'
import ExpandLessIcon from '@mui/icons-material/ExpandLess'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import HelpOutlineIcon from '@mui/icons-material/HelpOutline'
import SchemaIcon from '@mui/icons-material/Schema'
import UploadFileIcon from '@mui/icons-material/UploadFile'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Collapse,
  Divider,
  Grid,
  LinearProgress,
  List,
  ListItem,
  ListItemText,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import { useNavigate } from 'react-router-dom'
import {
  applyTemplateFromPaper,
  buildMetadataPatch,
  extractPaperMetadataStream,
  fetchPaperByDOI,
  generateExperimentCsv,
  generateStarterYaml,
  getPaperTemplateSuggestions,
  getStoredPaperExtraction,
  saveMetadata,
  storePaperExtraction,
} from '../api/client'
import type { PaperExtraction } from '../store/useStore'
import { useStore } from '../store/useStore'

const ARRIVE_LABELS: Record<string, string> = {
  study_design: 'Study Design',
  sample_size: 'Sample Size',
  inclusion_exclusion_criteria: 'Inclusion / Exclusion Criteria',
  randomisation: 'Randomisation',
  blinding: 'Blinding',
  outcome_measures: 'Outcome Measures',
  statistical_methods: 'Statistical Methods',
  experimental_animals: 'Experimental Animals',
  housing_husbandry: 'Housing & Husbandry',
  ethics_statement: 'Ethics Statement',
  adverse_events: 'Adverse Events',
  interpretation: 'Interpretation / Findings',
}

function StatusChip({ status }: { status: 'found' | 'inferred' | 'missing' }) {
  const map = {
    found: { label: 'Found', color: 'success' as const, icon: <CheckCircleIcon sx={{ fontSize: 14 }} /> },
    inferred: { label: 'Inferred', color: 'warning' as const, icon: <HelpOutlineIcon sx={{ fontSize: 14 }} /> },
    missing: { label: 'Missing', color: 'default' as const, icon: <ErrorIcon sx={{ fontSize: 14 }} /> },
  }
  const { label, color, icon } = map[status]
  return (
    <Chip
      size="small"
      label={label}
      color={color}
      icon={icon}
      sx={{ fontSize: 11, height: 22 }}
    />
  )
}

function MetaRow({ label, value }: { label: string; value: string | string[] | null }) {
  const display = Array.isArray(value) ? value.join(', ') : value
  return (
    <Box sx={{ mb: 1.5 }}>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.25 }}>
        {label}
      </Typography>
      <Typography variant="body2" sx={{ color: display ? 'text.primary' : 'text.disabled', fontStyle: display ? 'normal' : 'italic' }}>
        {display || 'Not found'}
      </Typography>
    </Box>
  )
}

function DropZone({ onFile }: { onFile: (f: File) => void }) {
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
      onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      onClick={() => inputRef.current?.click()}
      sx={{
        border: '2px dashed',
        borderColor: dragging ? 'primary.main' : 'grey.300',
        borderRadius: 3,
        p: 6,
        textAlign: 'center',
        cursor: 'pointer',
        bgcolor: dragging ? 'primary.50' : 'grey.50',
        transition: 'all 0.15s',
        '&:hover': { borderColor: 'primary.light', bgcolor: 'primary.50' },
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".pdf"
        style={{ display: 'none' }}
        onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f) }}
      />
      <UploadFileIcon sx={{ fontSize: 52, color: 'primary.light', mb: 1.5 }} />
      <Typography variant="h6" gutterBottom>
        Drop your PDF here or click to browse
      </Typography>
      <Typography variant="body2" color="text.secondary">
        Supports published papers, preprints, and protocols (PDF only)
      </Typography>
    </Box>
  )
}

function ARRIVEChecklist({ arrive }: { arrive: Record<string, { value: string | null; status: string }> }) {
  const fields = Object.entries(ARRIVE_LABELS)
  const found = fields.filter(([k]) => arrive[k]?.status === 'found').length
  const inferred = fields.filter(([k]) => arrive[k]?.status === 'inferred').length
  const missing = fields.filter(([k]) => arrive[k]?.status === 'missing').length

  return (
    <Card variant="outlined">
      <CardContent>
        <Stack direction="row" alignItems="center" spacing={1} mb={1}>
          <Typography variant="subtitle1" fontWeight={600}>
            ARRIVE 2.0 Checklist
          </Typography>
          <Tooltip title="ARRIVE (Animal Research: Reporting of In Vivo Experiments) guidelines help ensure reproducibility of animal research">
            <HelpOutlineIcon sx={{ fontSize: 16, color: 'text.secondary' }} />
          </Tooltip>
        </Stack>
        <Stack direction="row" spacing={1} mb={2}>
          <Chip size="small" label={`${found} found`} color="success" />
          <Chip size="small" label={`${inferred} inferred`} color="warning" />
          <Chip size="small" label={`${missing} missing`} color="default" />
        </Stack>
        <List dense disablePadding>
          {fields.map(([key, label], idx) => {
            const field = arrive[key] ?? { value: null, status: 'missing' }
            return (
              <Box key={key}>
                {idx > 0 && <Divider />}
                <ListItem disablePadding sx={{ py: 0.75, alignItems: 'flex-start' }}>
                  <ListItemText
                    primary={
                      <Stack direction="row" spacing={1} alignItems="center">
                        <Typography variant="body2" fontWeight={500}>{label}</Typography>
                        <StatusChip status={field.status as 'found' | 'inferred' | 'missing'} />
                      </Stack>
                    }
                    secondary={
                      field.value ? (
                        <Typography variant="caption" color="text.secondary" sx={{ mt: 0.25, display: 'block' }}>
                          {field.value}
                        </Typography>
                      ) : null
                    }
                  />
                </ListItem>
              </Box>
            )
          })}
        </List>
      </CardContent>
    </Card>
  )
}

function VCGHintsCard({ hints }: { hints: PaperExtraction['vcg_hints'] }) {
  const hasHints =
    hints.treatment_column_name ||
    hints.control_group_label ||
    hints.outcome_columns.length > 0

  return (
    <Card variant="outlined">
      <CardContent>
        <Typography variant="subtitle1" fontWeight={600} mb={1.5}>
          VCG Configuration Hints
        </Typography>
        {hasHints ? (
          <>
            <MetaRow label="Treatment / Group Column" value={hints.treatment_column_name} />
            <MetaRow label="Control Group Label" value={hints.control_group_label} />
            <MetaRow label="Treatment Group Label" value={hints.treatment_group_label} />
            <MetaRow label="Suggested Outcome Columns" value={hints.outcome_columns.length ? hints.outcome_columns : null} />
            <MetaRow label="Suggested Covariate Columns" value={hints.covariate_columns.length ? hints.covariate_columns : null} />
            <Stack direction="row" spacing={2} mt={1}>
              {hints.n_control != null && (
                <Chip size="small" label={`n control = ${hints.n_control}`} variant="outlined" />
              )}
              {hints.n_treatment != null && (
                <Chip size="small" label={`n treatment = ${hints.n_treatment}`} variant="outlined" />
              )}
            </Stack>
          </>
        ) : (
          <Typography variant="body2" color="text.secondary" fontStyle="italic">
            No VCG column hints could be inferred from this paper.
          </Typography>
        )}
        <Alert severity="info" sx={{ mt: 2, fontSize: 12 }}>
          These are suggestions based on the paper text. The VCG wizard lets you confirm or
          override each column assignment when you have your CSV loaded.
        </Alert>
      </CardContent>
    </Card>
  )
}

interface FieldMapping {
  field_id: string
  label: string
  arrive_section: string
  value: string | null
  source: string | null
  status: 'filled' | 'missing'
  severity: string
  is_column: boolean
}

interface TemplateCandidate {
  id: string
  name: string
  version: string
  description: string
  score: number
  reasons: string[]
  field_mapping: FieldMapping[]
}

function ScoreBar({ score }: { score: number }) {
  const pct = Math.round(score * 100)
  const color = pct >= 70 ? 'success' : pct >= 40 ? 'warning' : 'error'
  return (
    <Stack direction="row" alignItems="center" spacing={1} sx={{ minWidth: 160 }}>
      <LinearProgress
        variant="determinate"
        value={pct}
        color={color}
        sx={{ flex: 1, height: 8, borderRadius: 4 }}
      />
      <Typography variant="caption" fontWeight={600} sx={{ minWidth: 32 }}>
        {pct}%
      </Typography>
    </Stack>
  )
}

function FieldMappingTable({ mapping }: { mapping: FieldMapping[] }) {
  const metaFields = mapping.filter((f) => !f.is_column)
  const colFields = mapping.filter((f) => f.is_column)

  const renderRows = (rows: FieldMapping[]) =>
    rows.map((f) => (
      <TableRow key={f.field_id} sx={{ '&:last-child td': { border: 0 } }}>
        <TableCell sx={{ py: 0.75, fontSize: 12 }}>
          <Box>
            <Typography variant="caption" fontWeight={500}>{f.label}</Typography>
            {f.arrive_section && (
              <Typography variant="caption" color="text.secondary" display="block">
                {f.arrive_section}
              </Typography>
            )}
          </Box>
        </TableCell>
        <TableCell sx={{ py: 0.75, fontSize: 12, maxWidth: 260 }}>
          {f.value ? (
            <Typography variant="caption" sx={{ wordBreak: 'break-word' }}>
              {f.value.length > 120 ? f.value.slice(0, 120) + '…' : f.value}
            </Typography>
          ) : (
            <Typography variant="caption" color="text.disabled" fontStyle="italic">
              Not found in paper
            </Typography>
          )}
        </TableCell>
        <TableCell sx={{ py: 0.75 }}>
          <Chip
            size="small"
            label={f.status === 'filled' ? 'Filled' : 'Missing'}
            color={f.status === 'filled' ? 'success' : f.severity === 'high' ? 'error' : 'default'}
            sx={{ fontSize: 10, height: 20 }}
          />
        </TableCell>
      </TableRow>
    ))

  return (
    <Box sx={{ mt: 1.5, border: '1px solid', borderColor: 'divider', borderRadius: 1, overflow: 'hidden' }}>
      {metaFields.length > 0 && (
        <>
          <Typography variant="caption" fontWeight={600} sx={{ px: 1.5, py: 0.75, bgcolor: 'grey.50', display: 'block', borderBottom: '1px solid', borderColor: 'divider' }}>
            Metadata fields
          </Typography>
          <Table size="small">
            <TableHead>
              <TableRow sx={{ bgcolor: 'grey.50' }}>
                <TableCell sx={{ fontSize: 11, py: 0.5 }}>Template field</TableCell>
                <TableCell sx={{ fontSize: 11, py: 0.5 }}>Extracted value</TableCell>
                <TableCell sx={{ fontSize: 11, py: 0.5 }}>Status</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>{renderRows(metaFields)}</TableBody>
          </Table>
        </>
      )}
      {colFields.length > 0 && (
        <>
          <Typography variant="caption" fontWeight={600} sx={{ px: 1.5, py: 0.75, bgcolor: 'grey.50', display: 'block', borderTop: '1px solid', borderBottom: '1px solid', borderColor: 'divider' }}>
            Required columns
          </Typography>
          <Table size="small">
            <TableHead>
              <TableRow sx={{ bgcolor: 'grey.50' }}>
                <TableCell sx={{ fontSize: 11, py: 0.5 }}>Column field</TableCell>
                <TableCell sx={{ fontSize: 11, py: 0.5 }}>Matched from paper hints</TableCell>
                <TableCell sx={{ fontSize: 11, py: 0.5 }}>Status</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>{renderRows(colFields)}</TableBody>
          </Table>
        </>
      )}
    </Box>
  )
}

function TemplateSuggestionsCard({
  extraction,
  datasetId,
}: {
  extraction: object
  datasetId: string | null
}) {
  const [candidates, setCandidates] = useState<TemplateCandidate[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [appliedId, setAppliedId] = useState<string | null>(null)
  const [applyingId, setApplyingId] = useState<string | null>(null)
  const [downloadingId, setDownloadingId] = useState<string | null>(null)
  const [downloadingCsvId, setDownloadingCsvId] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getPaperTemplateSuggestions(extraction)
      .then((data) => {
        if (!cancelled) setCandidates(data.candidates ?? [])
      })
      .catch((err: any) => {
        const detail = err?.response?.data?.detail ?? err?.message ?? 'Unknown error'
        if (!cancelled) setError(`Template scoring failed: ${detail}`)
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [extraction])

  const handleApply = async (tid: string) => {
    if (!datasetId) return
    setApplyingId(tid)
    try {
      await applyTemplateFromPaper(datasetId, tid)
      setAppliedId(tid)
    } catch {
      setError(`Failed to assign template '${tid}'.`)
    } finally {
      setApplyingId(null)
    }
  }

  const handleDownloadYaml = async (tid: string) => {
    setDownloadingId(tid)
    try {
      const data = await generateStarterYaml(tid, extraction)
      const blob = new Blob([data.starter_yaml], { type: 'text/yaml' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${tid}-starter.yaml`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      setError('Failed to generate starter YAML.')
    } finally {
      setDownloadingId(null)
    }
  }

  const handleDownloadCsv = async (tid: string) => {
    setDownloadingCsvId(tid)
    try {
      const data = await generateExperimentCsv(tid, extraction)
      const blob = new Blob([data.csv], { type: 'text/csv' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = data.filename ?? `${tid}-experiment-template.csv`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      setError('Failed to generate CSV template.')
    } finally {
      setDownloadingCsvId(null)
    }
  }

  return (
    <Card variant="outlined">
      <CardContent>
        <Stack direction="row" alignItems="center" spacing={1} mb={1.5}>
          <SchemaIcon color="primary" sx={{ fontSize: 20 }} />
          <Typography variant="subtitle1" fontWeight={600}>
            Suggested Reporting Templates
          </Typography>
          <Tooltip title="Templates are scored against study type, species, ARRIVE field coverage, and keywords extracted from the paper.">
            <HelpOutlineIcon sx={{ fontSize: 16, color: 'text.secondary' }} />
          </Tooltip>
        </Stack>

        {loading && <CircularProgress size={22} />}
        {error && <Alert severity="warning" sx={{ fontSize: 12 }}>{error}</Alert>}

        {!loading && candidates.length === 0 && !error && (
          <Typography variant="body2" color="text.secondary" fontStyle="italic">
            No templates matched the paper content above the minimum threshold.
          </Typography>
        )}

        <Stack spacing={1.5}>
          {candidates.map((c) => {
            const isExpanded = expandedId === c.id
            const filled = c.field_mapping.filter((f) => f.status === 'filled').length
            const total = c.field_mapping.length

            return (
              <Box
                key={c.id}
                sx={{
                  border: '1px solid',
                  borderColor: appliedId === c.id ? 'success.main' : 'divider',
                  borderRadius: 2,
                  p: 1.5,
                  bgcolor: appliedId === c.id ? 'success.50' : 'background.paper',
                }}
              >
                <Stack direction="row" alignItems="flex-start" justifyContent="space-between" flexWrap="wrap" gap={1}>
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Stack direction="row" alignItems="center" spacing={1} flexWrap="wrap">
                      <Typography variant="body2" fontWeight={600}>{c.name}</Typography>
                      <Chip size="small" label={`v${c.version}`} variant="outlined" sx={{ fontSize: 10, height: 18 }} />
                      {appliedId === c.id && (
                        <Chip size="small" label="Applied" color="success" icon={<CheckCircleIcon sx={{ fontSize: 12 }} />} sx={{ fontSize: 10, height: 20 }} />
                      )}
                    </Stack>
                    <ScoreBar score={c.score} />
                    <Stack direction="row" spacing={0.5} flexWrap="wrap" mt={0.5}>
                      {c.reasons.map((r, i) => (
                        <Typography key={i} variant="caption" color="text.secondary">
                          · {r}
                        </Typography>
                      ))}
                    </Stack>
                    {total > 0 && (
                      <Typography variant="caption" color={filled === total ? 'success.main' : 'text.secondary'} sx={{ mt: 0.25, display: 'block' }}>
                        {filled}/{total} fields can be pre-filled from paper
                      </Typography>
                    )}
                  </Box>

                  <Stack direction="row" spacing={0.75} alignItems="center" flexShrink={0}>
                    <Tooltip title={!datasetId ? 'Upload a CSV first to assign a template to a dataset' : ''}>
                      <span>
                        <Button
                          size="small"
                          variant="contained"
                          disabled={!datasetId || applyingId === c.id || appliedId === c.id}
                          onClick={() => handleApply(c.id)}
                          sx={{ fontSize: 12, whiteSpace: 'nowrap' }}
                        >
                          {applyingId === c.id ? <CircularProgress size={14} /> : appliedId === c.id ? 'Applied' : 'Use template'}
                        </Button>
                      </span>
                    </Tooltip>
                    <Tooltip title="Download a blank CSV with the right column headers — fill it in with your experimental results and import it directly">
                      <Button
                        size="small"
                        variant="contained"
                        color="success"
                        disabled={downloadingCsvId === c.id}
                        onClick={() => handleDownloadCsv(c.id)}
                        startIcon={downloadingCsvId === c.id ? <CircularProgress size={12} /> : <DownloadIcon sx={{ fontSize: 14 }} />}
                        sx={{ fontSize: 12, whiteSpace: 'nowrap' }}
                      >
                        CSV Template
                      </Button>
                    </Tooltip>
                    <Tooltip title="Download a starter YAML schema — upload to Templates to reuse this configuration for future experiments">
                      <Button
                        size="small"
                        variant="outlined"
                        disabled={downloadingId === c.id}
                        onClick={() => handleDownloadYaml(c.id)}
                        startIcon={downloadingId === c.id ? <CircularProgress size={12} /> : <DownloadIcon sx={{ fontSize: 14 }} />}
                        sx={{ fontSize: 12, whiteSpace: 'nowrap' }}
                      >
                        YAML Schema
                      </Button>
                    </Tooltip>
                    {c.field_mapping.length > 0 && (
                      <Button
                        size="small"
                        variant="text"
                        onClick={() => setExpandedId(isExpanded ? null : c.id)}
                        endIcon={isExpanded ? <ExpandLessIcon sx={{ fontSize: 14 }} /> : <ExpandMoreIcon sx={{ fontSize: 14 }} />}
                        sx={{ fontSize: 12 }}
                      >
                        Mapping
                      </Button>
                    )}
                  </Stack>
                </Stack>

                <Collapse in={isExpanded}>
                  <FieldMappingTable mapping={c.field_mapping} />
                </Collapse>
              </Box>
            )
          })}
        </Stack>

        {appliedId && datasetId && (
          <Alert severity="success" sx={{ mt: 1.5, fontSize: 12 }}>
            Template assigned. Head to the <strong>Templates</strong> page to review the full conformance report, or continue with your CSV workflow.
          </Alert>
        )}
      </CardContent>
    </Card>
  )
}

export default function PaperImportPage() {
  const navigate = useNavigate()
  const { datasetId, paperExtraction, setPaperExtraction, setMetadata } = useStore()

  const [loading, setLoading] = useState(false)
  const [statusMessage, setStatusMessage] = useState<string>('')
  const [error, setError] = useState<string | null>(null)
  const [applySuccess, setApplySuccess] = useState(false)
  const [showArrive, setShowArrive] = useState(false)
  const [doi, setDoi] = useState('')
  const [doiLoading, setDoiLoading] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => () => { abortRef.current?.abort() }, [])

  // Restore persisted extraction when a dataset is loaded
  useEffect(() => {
    if (datasetId && !paperExtraction) {
      getStoredPaperExtraction(datasetId)
        .then((data) => { if (data) setPaperExtraction(data as PaperExtraction) })
        .catch(() => {})
    }
  }, [datasetId])

  const handleFile = async (file: File) => {
    abortRef.current?.abort()
    abortRef.current = new AbortController()
    setError(null)
    setApplySuccess(false)
    setLoading(true)
    setStatusMessage('Starting extraction…')
    try {
      await extractPaperMetadataStream(
        file,
        (msg) => setStatusMessage(msg),
        (data) => {
          const extraction = data as PaperExtraction
          setPaperExtraction(extraction)
          if (datasetId) {
            storePaperExtraction(datasetId, extraction).catch(() => {})
          }
          setLoading(false)
        },
        (msg) => {
          setError(msg)
          setLoading(false)
        },
        abortRef.current.signal,
      )
    } catch (err: any) {
      if (err?.name === 'AbortError') return
      const msg =
        err?.message ??
        'Extraction failed. Check that ANTHROPIC_API_KEY is configured on the server.'
      setError(msg)
      setLoading(false)
    }
  }

  const handleDOI = async () => {
    const trimmed = doi.trim()
    if (!trimmed) return
    setError(null)
    setApplySuccess(false)
    setDoiLoading(true)
    try {
      const data = await fetchPaperByDOI(trimmed)
      const extraction = data as PaperExtraction
      setPaperExtraction(extraction)
      if (datasetId) {
        storePaperExtraction(datasetId, extraction).catch(() => {})
      }
    } catch (err: any) {
      const msg =
        err?.response?.data?.detail ??
        err?.message ??
        'DOI lookup failed. Check the DOI and your network connection.'
      setError(msg)
    } finally {
      setDoiLoading(false)
    }
  }

  const handleApply = async () => {
    if (!paperExtraction || !datasetId) return
    try {
      const saved = await saveMetadata(datasetId, buildMetadataPatch(paperExtraction) as any)
      setMetadata(saved.metadata)
      setApplySuccess(true)
    } catch {
      setError('Failed to apply metadata to current session.')
    }
  }

  return (
    <Box>
      <Stack direction="row" alignItems="center" spacing={1.5} mb={1}>
        <ArticleIcon color="primary" sx={{ fontSize: 32 }} />
        <Box>
          <Typography variant="h5">Paper Import</Typography>
          <Typography variant="body2" color="text.secondary">
            Upload a publication PDF to extract metadata and pre-fill your FAIR schema and VCG configuration
          </Typography>
        </Box>
      </Stack>

      <Divider sx={{ mb: 3 }} />

      {!paperExtraction && !loading && (
        <>
          <Alert severity="info" sx={{ mb: 3 }}>
            This feature sends the <strong>full PDF</strong> directly to the Claude API for
            layout-aware processing (no text pre-extraction step). An{' '}
            <strong>ANTHROPIC_API_KEY</strong> must be set in the backend environment.
            Do not upload unpublished or confidential manuscripts. Max file size: 32 MB.
          </Alert>
          <DropZone onFile={handleFile} />

          <Divider sx={{ my: 3 }}>
            <Typography variant="caption" color="text.secondary">or enter a DOI</Typography>
          </Divider>

          <Stack direction="row" spacing={1} alignItems="flex-start">
            <TextField
              size="small"
              fullWidth
              label="DOI"
              placeholder="10.1234/example or https://doi.org/10.1234/example"
              value={doi}
              onChange={(e) => setDoi(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handleDOI() }}
              helperText="Fetches bibliographic metadata from CrossRef (no PDF required, no API key needed)"
            />
            <Button
              variant="outlined"
              onClick={handleDOI}
              disabled={doiLoading || !doi.trim()}
              sx={{ mt: 0.25, whiteSpace: 'nowrap', minWidth: 120 }}
            >
              {doiLoading ? <CircularProgress size={18} /> : 'Fetch DOI'}
            </Button>
          </Stack>
        </>
      )}

      {loading && (
        <Box textAlign="center" py={8}>
          <CircularProgress size={52} sx={{ mb: 2 }} />
          <Typography variant="h6" gutterBottom>Analysing paper…</Typography>
          <Typography variant="body2" color="text.secondary">
            {statusMessage || 'Extracting metadata — this usually takes 10–30 seconds.'}
          </Typography>
        </Box>
      )}

      {error && (
        <Alert
          severity="error"
          sx={{ mt: 2 }}
          action={
            <Button size="small" onClick={() => setError(null)}>
              Try Again
            </Button>
          }
        >
          {error}
        </Alert>
      )}

      {paperExtraction && !loading && (
        <Box>
          {/* Header bar */}
          <Card sx={{ mb: 3, bgcolor: 'primary.50', border: '1px solid', borderColor: 'primary.200' }}>
            <CardContent sx={{ py: '12px !important' }}>
              <Stack direction="row" alignItems="center" justifyContent="space-between" flexWrap="wrap" gap={1}>
                <Box>
                  <Typography variant="subtitle1" fontWeight={600}>
                    {paperExtraction._filename}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {paperExtraction._method === 'crossref_doi'
                      ? 'Bibliographic metadata via CrossRef · ARRIVE fields require full PDF'
                      : `${paperExtraction._file_size_kb} KB · processed natively by Claude (layout-aware) · extraction complete`}
                  </Typography>
                </Box>
                <Stack direction="row" spacing={1}>
                  <Button
                    size="small"
                    variant="outlined"
                    onClick={() => { setPaperExtraction(null); setApplySuccess(false) }}
                  >
                    Import Different Paper
                  </Button>
                  {datasetId && (
                    <Button
                      size="small"
                      variant="contained"
                      onClick={handleApply}
                    >
                      Apply to Current Dataset
                    </Button>
                  )}
                  {!datasetId && (
                    <Button
                      size="small"
                      variant="contained"
                      onClick={() => navigate('/')}
                    >
                      Upload CSV Now
                    </Button>
                  )}
                </Stack>
              </Stack>
            </CardContent>
          </Card>

          <Collapse in={applySuccess}>
            <Alert severity="success" sx={{ mb: 2 }} onClose={() => setApplySuccess(false)}>
              Metadata applied to current dataset. Head to the{' '}
              <strong>Metadata Wizard</strong> to review and complete the fields.
            </Alert>
          </Collapse>

          {!datasetId && (
            <Alert severity="info" sx={{ mb: 2 }}>
              No CSV dataset is loaded yet. The extraction is stored in this session — upload
              your CSV and then return here to apply it.
            </Alert>
          )}

          {/* Summary */}
          <Card variant="outlined" sx={{ mb: 2 }}>
            <CardContent>
              <Typography variant="subtitle1" fontWeight={600} mb={0.5}>
                Summary
              </Typography>
              <Typography variant="body2">{paperExtraction.summary}</Typography>
            </CardContent>
          </Card>

          <Grid container spacing={2} mb={2}>
            {/* Dataset Metadata */}
            <Grid item xs={12} md={6}>
              <Card variant="outlined" sx={{ height: '100%' }}>
                <CardContent>
                  <Typography variant="subtitle1" fontWeight={600} mb={1.5}>
                    Dataset Metadata
                  </Typography>
                  <MetaRow label="Title" value={paperExtraction.dataset_metadata.title} />
                  <MetaRow label="Description" value={paperExtraction.dataset_metadata.description} />
                  <MetaRow label="Creator / First Author" value={paperExtraction.dataset_metadata.creator} />
                  <MetaRow label="Institution" value={paperExtraction.dataset_metadata.institution} />
                  <MetaRow label="Species" value={paperExtraction.dataset_metadata.species} />
                  <MetaRow label="Study Type" value={paperExtraction.dataset_metadata.study_type} />
                  <MetaRow label="Keywords" value={paperExtraction.dataset_metadata.keywords} />
                  <MetaRow label="License" value={paperExtraction.dataset_metadata.license} />
                  <MetaRow label="Funding Source" value={paperExtraction.dataset_metadata.funding_source} />
                  <MetaRow label="Protocol / Preregistration" value={paperExtraction.dataset_metadata.protocol_reference} />
                </CardContent>
              </Card>
            </Grid>

            {/* VCG Hints */}
            <Grid item xs={12} md={6}>
              <VCGHintsCard hints={paperExtraction.vcg_hints} />
            </Grid>
          </Grid>

          {/* Template suggestions */}
          <Box sx={{ mb: 2 }}>
            <TemplateSuggestionsCard extraction={paperExtraction} datasetId={datasetId} />
          </Box>

          {/* ARRIVE checklist — collapsible */}
          <Box>
            <Button
              variant="outlined"
              size="small"
              onClick={() => setShowArrive((v) => !v)}
              sx={{ mb: 1.5 }}
            >
              {showArrive ? 'Hide' : 'Show'} ARRIVE 2.0 Checklist
            </Button>
            <Collapse in={showArrive}>
              <ARRIVEChecklist arrive={paperExtraction.arrive} />
            </Collapse>
          </Box>
        </Box>
      )}
    </Box>
  )
}
