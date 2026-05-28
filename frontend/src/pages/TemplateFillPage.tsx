import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import CloseIcon from '@mui/icons-material/Close'
import DescriptionIcon from '@mui/icons-material/Description'
import DownloadIcon from '@mui/icons-material/Download'
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline'
import ExpandLessIcon from '@mui/icons-material/ExpandLess'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import LightbulbIcon from '@mui/icons-material/Lightbulb'
import RefreshIcon from '@mui/icons-material/Refresh'
import TipsAndUpdatesIcon from '@mui/icons-material/TipsAndUpdates'
import UploadFileIcon from '@mui/icons-material/UploadFile'
import WarningAmberIcon from '@mui/icons-material/WarningAmber'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
  Chip,
  CircularProgress,
  Collapse,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Drawer,
  FormControl,
  FormControlLabel,
  Grid,
  IconButton,
  InputLabel,
  LinearProgress,
  MenuItem,
  Paper,
  Select,
  Snackbar,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { ChangeEvent } from 'react'
import {
  arriveExportUrl,
  extractTemplateFromDocument,
  fillTemplateFromPaper,
  getTemplateCompletion,
  llmSuggestTemplate,
  prepareExportUrl,
  saveMetadata,
} from '../api/client'
import type {
  TemplateCompletionField,
  TemplateCompletionReport,
  TemplateSuggestion,
} from '../api/client'
import { useStore } from '../store/useStore'

type SortKey = 'section' | 'severity' | 'status'

const STATUS_COLOR: Record<TemplateCompletionField['status'], 'success' | 'warning' | 'error'> = {
  satisfied: 'success',
  partial: 'warning',
  missing: 'error',
}

const SEVERITY_COLOR: Record<
  TemplateCompletionField['severity'],
  'error' | 'warning' | 'default'
> = {
  high: 'error',
  medium: 'warning',
  low: 'default',
}

const SEVERITY_RANK: Record<TemplateCompletionField['severity'], number> = {
  high: 0,
  medium: 1,
  low: 2,
}

const STATUS_RANK: Record<TemplateCompletionField['status'], number> = {
  missing: 0,
  partial: 1,
  satisfied: 2,
}

const DRAWER_TOP = { xs: 56, sm: 64 }

const SECTION_CHIP_SX = {
  maxWidth: '100%',
  height: 'auto',
  minHeight: 24,
  alignItems: 'flex-start',
  '& .MuiChip-label': {
    display: 'block',
    overflow: 'visible',
    textOverflow: 'clip',
    whiteSpace: 'normal',
    py: 0.25,
  },
}

type PendingSuggestion = TemplateSuggestion & {
  _id: string
  source: 'llm' | 'document'
}

function errorMessage(err: unknown, fallback: string): string {
  // axios errors have err.response.data.detail (FastAPI HTTPException shape)
  const ax = err as { response?: { data?: { detail?: string } }; message?: string }
  const detail = ax?.response?.data?.detail
  if (typeof detail === 'string' && detail) return `${fallback}: ${detail}`
  if (ax?.message) return `${fallback}: ${ax.message}`
  return fallback
}

function StatusIcon({ field }: { field: TemplateCompletionField }) {
  if (field.status === 'satisfied') {
    return (
      <Tooltip
        title={
          field.via_crosswalk
            ? `Satisfied via crosswalk (${field.satisfied_by_field ?? ''})`
            : 'Satisfied'
        }
      >
        <CheckCircleIcon
          fontSize="small"
          color={field.via_crosswalk ? 'info' : 'success'}
        />
      </Tooltip>
    )
  }
  if (field.status === 'partial') {
    return (
      <Tooltip title="Partial">
        <WarningAmberIcon fontSize="small" color="warning" />
      </Tooltip>
    )
  }
  return (
    <Tooltip title="Missing">
      <ErrorOutlineIcon fontSize="small" color="error" />
    </Tooltip>
  )
}

function SectionChips({ field }: { field: TemplateCompletionField }) {
  const hasArrive = !!field.arrive_section
  const hasPrepare = !!field.prepare_section
  if (!hasArrive && !hasPrepare) {
    return (
      <Typography variant="caption" color="text.secondary">
        —
      </Typography>
    )
  }
  return (
    <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', minWidth: 0 }}>
      {hasPrepare && (
        <Chip
          label={`PREPARE: ${field.prepare_section}`}
          size="small"
          color="warning"
          sx={SECTION_CHIP_SX}
        />
      )}
      {hasArrive && (
        <Chip
          label={`ARRIVE: ${field.arrive_section}`}
          size="small"
          color="info"
          sx={SECTION_CHIP_SX}
        />
      )}
    </Box>
  )
}

function ProgressSegments({ totals }: { totals: TemplateCompletionReport['totals'] }) {
  const total = Math.max(totals.total, 1)
  const segs: Array<{ label: string; count: number; color: string }> = [
    { label: 'Direct', count: totals.satisfied_direct, color: '#2e7d32' },
    { label: 'Crosswalk', count: totals.satisfied_via_crosswalk, color: '#0288d1' },
    { label: 'Partial', count: totals.partial, color: '#ed6c02' },
    { label: 'Missing', count: totals.missing, color: '#d32f2f' },
  ]
  return (
    <Box>
      <Box
        sx={{
          display: 'flex',
          height: 16,
          width: '100%',
          borderRadius: 1,
          overflow: 'hidden',
          border: '1px solid rgba(0,0,0,0.12)',
        }}
      >
        {segs.map((s) => {
          const pct = (s.count / total) * 100
          if (pct <= 0) return null
          return (
            <Tooltip key={s.label} title={`${s.label}: ${s.count} / ${totals.total}`}>
              <Box
                sx={{
                  width: `${pct}%`,
                  bgcolor: s.color,
                  transition: 'width 0.3s ease',
                }}
              />
            </Tooltip>
          )
        })}
      </Box>
      <Box sx={{ display: 'flex', gap: 2, mt: 1, flexWrap: 'wrap' }}>
        {segs.map((s) => (
          <Box key={s.label} sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <Box sx={{ width: 10, height: 10, bgcolor: s.color, borderRadius: 0.5 }} />
            <Typography variant="caption" color="text.secondary">
              {s.label}: <strong>{s.count}</strong>
            </Typography>
          </Box>
        ))}
      </Box>
    </Box>
  )
}

export default function TemplateFillPage() {
  const navigate = useNavigate()
  const {
    datasetId,
    templateId,
    templateCompletion,
    setTemplateCompletion,
    paperExtraction,
    llmEnabled,
    setMetadata,
  } = useStore()

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const [sortKey, setSortKey] = useState<SortKey>('section')
  const [statusFilter, setStatusFilter] = useState<'all' | 'missing' | 'partial' | 'satisfied'>(
    'all',
  )

  // Drawer state
  const [drawerField, setDrawerField] = useState<TemplateCompletionField | null>(null)
  const [drawerValue, setDrawerValue] = useState('')
  const [drawerSaving, setDrawerSaving] = useState(false)

  // LLM dialog
  const [llmDialogOpen, setLlmDialogOpen] = useState(false)
  const [llmSelectedFields, setLlmSelectedFields] = useState<Set<string>>(new Set())
  const [llmBusy, setLlmBusy] = useState(false)

  // Action busy flags
  const [fillBusy, setFillBusy] = useState(false)
  const [docBusy, setDocBusy] = useState(false)
  // Per-row busy: field_id currently waiting on a single-field LLM call
  const [rowLlmBusy, setRowLlmBusy] = useState<string | null>(null)

  // Suggestions
  const [pendingSuggestions, setPendingSuggestions] = useState<PendingSuggestion[]>([])
  const [suggestionsOpen, setSuggestionsOpen] = useState(true)

  const fileInputRef = useRef<HTMLInputElement | null>(null)

  const refreshCompletion = async (): Promise<TemplateCompletionReport | null> => {
    if (!datasetId || !templateId) {
      setTemplateCompletion(null)
      return null
    }
    setLoading(true)
    setError(null)
    try {
      const r = await getTemplateCompletion(datasetId)
      setTemplateCompletion(r)
      return r
    } catch (e) {
      setError(errorMessage(e, 'Failed to load completion report'))
      return null
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refreshCompletion()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetId, templateId])

  const fieldsById = useMemo(() => {
    const m = new Map<string, TemplateCompletionField>()
    if (templateCompletion) {
      for (const f of templateCompletion.fields) m.set(f.field_id, f)
    }
    return m
  }, [templateCompletion])

  const sortedFields = useMemo(() => {
    if (!templateCompletion) return []
    const filtered = templateCompletion.fields.filter((f) =>
      statusFilter === 'all' ? true : f.status === statusFilter,
    )
    const copy = [...filtered]
    copy.sort((a, b) => {
      if (sortKey === 'severity') {
        return SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity]
      }
      if (sortKey === 'status') {
        return STATUS_RANK[a.status] - STATUS_RANK[b.status]
      }
      // section: arrive first, then prepare, then label
      const aSec = a.arrive_section ?? a.prepare_section ?? '~'
      const bSec = b.arrive_section ?? b.prepare_section ?? '~'
      const aKind = a.arrive_section ? 0 : 1
      const bKind = b.arrive_section ? 0 : 1
      if (aKind !== bKind) return aKind - bKind
      if (aSec !== bSec) return aSec.localeCompare(bSec)
      return a.label.localeCompare(b.label)
    })
    return copy
  }, [templateCompletion, sortKey, statusFilter])

  const arriveSections = useMemo(
    () => templateCompletion?.by_section.filter((s) => s.kind === 'arrive') ?? [],
    [templateCompletion],
  )
  const prepareSections = useMemo(
    () => templateCompletion?.by_section.filter((s) => s.kind === 'prepare') ?? [],
    [templateCompletion],
  )

  // ── Action handlers ─────────────────────────────────────────────────────

  const handleFillFromPaper = async () => {
    if (!datasetId) return
    setFillBusy(true)
    setError(null)
    try {
      const result = await fillTemplateFromPaper(datasetId)
      setTemplateCompletion(result.completion)
      setToast(`Filled ${result.filled.length} field(s) from paper.`)
    } catch (e) {
      setError(errorMessage(e, 'Failed to fill from paper'))
    } finally {
      setFillBusy(false)
    }
  }

  const openLlmDialog = () => {
    if (!templateCompletion) return
    // Default: all missing + partial
    const defaults = new Set(
      templateCompletion.fields
        .filter((f) => f.status === 'missing' || f.status === 'partial')
        .map((f) => f.field_id),
    )
    setLlmSelectedFields(defaults)
    setLlmDialogOpen(true)
  }

  const handleLlmRun = async () => {
    if (!datasetId) return
    setLlmBusy(true)
    setError(null)
    try {
      const ids = Array.from(llmSelectedFields)
      const result = await llmSuggestTemplate(datasetId, ids.length ? ids : null)
      const stamped: PendingSuggestion[] = result.suggestions.map((s, i) => ({
        ...s,
        _id: `llm-${Date.now()}-${i}`,
        source: 'llm',
      }))
      setPendingSuggestions((prev) => [...stamped, ...prev])
      setSuggestionsOpen(true)
      setLlmDialogOpen(false)
      setToast(`Received ${stamped.length} suggestion(s).`)
    } catch (e) {
      setError(errorMessage(e, 'LLM suggestion failed'))
    } finally {
      setLlmBusy(false)
    }
  }

  const handleDocumentUpload = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !datasetId) return
    setDocBusy(true)
    setError(null)
    try {
      const result = await extractTemplateFromDocument(datasetId, file)
      const stamped: PendingSuggestion[] = result.suggestions.map((s, i) => ({
        ...s,
        _id: `doc-${Date.now()}-${i}`,
        source: 'document',
      }))
      setPendingSuggestions((prev) => [...stamped, ...prev])
      setSuggestionsOpen(true)
      setToast(`Extracted ${stamped.length} suggestion(s) from ${file.name}.`)
    } catch (e) {
      setError(errorMessage(e, 'Document extraction failed'))
    } finally {
      setDocBusy(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const acceptSuggestion = async (s: PendingSuggestion) => {
    if (!datasetId) return
    if (s.value == null) return
    try {
      const result = await saveMetadata(datasetId, { [s.field_id]: s.value } as Record<
        string,
        unknown
      >)
      setMetadata(result.metadata)
      setPendingSuggestions((prev) => prev.filter((p) => p._id !== s._id))
      setToast(`Accepted suggestion for ${s.field_id}.`)
      await refreshCompletion()
    } catch (e) {
      setError(errorMessage(e, `Failed to save suggestion for ${s.field_id}`))
    }
  }

  const editSuggestion = (s: PendingSuggestion) => {
    const field = fieldsById.get(s.field_id)
    if (!field) {
      setError(`Unknown field: ${s.field_id}`)
      return
    }
    setDrawerField(field)
    setDrawerValue(s.value ?? '')
    // Keep the suggestion in the pending queue so a cancelled drawer
    // doesn't silently drop it; it gets cleared on successful save in
    // handleDrawerSave below.
  }

  const rejectSuggestion = (s: PendingSuggestion) => {
    setPendingSuggestions((prev) => prev.filter((p) => p._id !== s._id))
  }

  // ── Drawer handlers ─────────────────────────────────────────────────────

  const openDrawer = (field: TemplateCompletionField) => {
    setDrawerField(field)
    setDrawerValue(field.value ?? '')
  }

  const closeDrawer = () => {
    setDrawerField(null)
    setDrawerValue('')
  }

  const handleDrawerSave = async () => {
    if (!datasetId || !drawerField) return
    setDrawerSaving(true)
    setError(null)
    try {
      const result = await saveMetadata(datasetId, {
        [drawerField.field_id]: drawerValue,
      } as Record<string, unknown>)
      setMetadata(result.metadata)
      // Drop any pending suggestion(s) for this field — the user has now
      // taken ownership of the value via the drawer.
      const savedFieldId = drawerField.field_id
      setPendingSuggestions((prev) => prev.filter((p) => p.field_id !== savedFieldId))
      setToast(`Saved ${drawerField.field_id}.`)
      closeDrawer()
      await refreshCompletion()
    } catch (e) {
      setError(errorMessage(e, `Failed to save ${drawerField.field_id}`))
    } finally {
      setDrawerSaving(false)
    }
  }

  const requestLlmForField = async (field: TemplateCompletionField) => {
    if (!datasetId) return
    setRowLlmBusy(field.field_id)
    try {
      const result = await llmSuggestTemplate(datasetId, [field.field_id])
      const stamped: PendingSuggestion[] = result.suggestions.map((s, i) => ({
        ...s,
        _id: `llm-${Date.now()}-${i}`,
        source: 'llm',
      }))
      setPendingSuggestions((prev) => [...stamped, ...prev])
      setSuggestionsOpen(true)
      setToast(`Got ${stamped.length} suggestion(s) for ${field.label}.`)
    } catch (e) {
      setError(errorMessage(e, `LLM suggestion failed for ${field.field_id}`))
    } finally {
      setRowLlmBusy(null)
    }
  }

  const useHintForField = (field: TemplateCompletionField) => {
    if (!field.paper_hint) return
    openDrawer(field)
    setDrawerValue(field.paper_hint)
  }

  // ── Empty / Loading states ──────────────────────────────────────────────

  if (!datasetId) {
    return (
      <Box>
        <Alert
          severity="info"
          action={
            <Button color="inherit" size="small" onClick={() => navigate('/')}>
              Upload CSV
            </Button>
          }
        >
          Upload a dataset to start filling a template.
        </Alert>
      </Box>
    )
  }

  if (!templateId) {
    return (
      <Box>
        <Box sx={{ mb: 3 }}>
          <Typography variant="h5">Template Fill</Typography>
          <Typography variant="body2" color="text.secondary">
            Focused workspace for completing your assigned template.
          </Typography>
        </Box>
        <Alert
          severity="info"
          action={
            <Button color="inherit" size="small" onClick={() => navigate('/templates')}>
              Go to Templates
            </Button>
          }
        >
          No template assigned. Assign one to begin filling required metadata.
        </Alert>
      </Box>
    )
  }

  if (loading && !templateCompletion) {
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mt: 4 }}>
        <CircularProgress size={20} />
        <Typography variant="body2" color="text.secondary">
          Loading completion report…
        </Typography>
      </Box>
    )
  }

  if (!templateCompletion) {
    return (
      <Alert severity="error" onClose={() => setError(null)}>
        {error ?? 'No completion report available.'}
      </Alert>
    )
  }

  const totals = templateCompletion.totals

  // ── Render ──────────────────────────────────────────────────────────────

  return (
    <Box sx={{ maxWidth: '100%', minWidth: 0 }}>
      {/* Header */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 3, gap: 2, flexWrap: 'wrap' }}>
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="h5">
            Template Fill — {templateCompletion.template_name}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Complete required fields from your paper, an external document, or the LLM assistant.
          </Typography>
        </Box>
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          <Button
            variant="outlined"
            startIcon={<RefreshIcon />}
            onClick={refreshCompletion}
            disabled={loading}
          >
            Refresh
          </Button>
          <Button
            variant="outlined"
            startIcon={<ArrowBackIcon />}
            onClick={() => navigate('/templates')}
          >
            Back to Templates
          </Button>
        </Stack>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* Summary Card */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Grid container spacing={3}>
            <Grid item xs={12} md={7}>
              <Typography variant="overline" color="text.secondary">
                Completion
              </Typography>
              <Box sx={{ mt: 1 }}>
                <ProgressSegments totals={totals} />
              </Box>
              <Box sx={{ display: 'flex', gap: 3, mt: 2, flexWrap: 'wrap' }}>
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    Total fields
                  </Typography>
                  <Typography variant="h6">{totals.total}</Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    Satisfied
                  </Typography>
                  <Typography variant="h6" color="success.main">
                    {totals.satisfied_direct + totals.satisfied_via_crosswalk}
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    Partial
                  </Typography>
                  <Typography variant="h6" color="warning.main">
                    {totals.partial}
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    Missing
                  </Typography>
                  <Typography variant="h6" color="error.main">
                    {totals.missing}
                  </Typography>
                </Box>
              </Box>
            </Grid>
            <Grid item xs={12} md={5}>
              <Typography variant="overline" color="text.secondary">
                By Severity
              </Typography>
              <Stack spacing={1.5} sx={{ mt: 1 }}>
                {(['high', 'medium', 'low'] as const).map((sev) => {
                  const row = templateCompletion.by_severity[sev]
                  const pct = row.total > 0 ? (row.satisfied / row.total) * 100 : 0
                  return (
                    <Box key={sev}>
                      <Box
                        sx={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          mb: 0.5,
                        }}
                      >
                        <Chip
                          label={sev}
                          size="small"
                          color={SEVERITY_COLOR[sev]}
                          sx={{ textTransform: 'capitalize' }}
                        />
                        <Typography variant="caption" color="text.secondary">
                          {row.satisfied} / {row.total}
                        </Typography>
                      </Box>
                      <LinearProgress
                        variant="determinate"
                        value={pct}
                        color={SEVERITY_COLOR[sev] === 'default' ? 'inherit' : SEVERITY_COLOR[sev]}
                        sx={{ height: 6, borderRadius: 1 }}
                      />
                    </Box>
                  )
                })}
              </Stack>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {/* Section Progress */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Section Progress
          </Typography>
          <Grid container spacing={3}>
            {[
              { label: 'ARRIVE 2.0', sections: arriveSections, color: 'info' as const },
              { label: 'PREPARE', sections: prepareSections, color: 'warning' as const },
            ].map((group) => (
              <Grid item xs={12} md={6} key={group.label}>
                <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>
                  {group.label}
                </Typography>
                {group.sections.length === 0 ? (
                  <Typography variant="caption" color="text.secondary">
                    No sections.
                  </Typography>
                ) : (
                  <Stack spacing={1.5}>
                    {group.sections.map((s) => {
                      const pct = s.total > 0 ? (s.satisfied / s.total) * 100 : 0
                      return (
                        <Box key={s.label}>
                          <Box
                            sx={{
                              display: 'flex',
                              justifyContent: 'space-between',
                              alignItems: 'center',
                              mb: 0.25,
                            }}
                          >
                            <Typography variant="body2" fontWeight={500}>
                              {s.label}
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                              {s.satisfied} / {s.total}
                            </Typography>
                          </Box>
                          <LinearProgress
                            variant="determinate"
                            value={pct}
                            color={group.color}
                            sx={{ height: 5, borderRadius: 1 }}
                          />
                        </Box>
                      )
                    })}
                  </Stack>
                )}
              </Grid>
            ))}
          </Grid>
        </CardContent>
      </Card>

      {/* Bulk Action Toolbar */}
      <Paper variant="outlined" sx={{ p: 1.5, mb: 2, position: 'sticky', top: DRAWER_TOP, zIndex: 2, bgcolor: 'background.paper' }}>
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          <Tooltip
            title={paperExtraction ? 'Bulk-fill fields from the imported paper' : 'Import a paper first'}
          >
            <span>
              <Button
                variant="contained"
                size="small"
                startIcon={fillBusy ? <CircularProgress size={14} color="inherit" /> : <DescriptionIcon />}
                onClick={handleFillFromPaper}
                disabled={!paperExtraction || fillBusy}
              >
                Fill from paper
              </Button>
            </span>
          </Tooltip>
          <Tooltip title={llmEnabled === false ? 'LLM is disabled' : 'Get AI suggestions for selected fields'}>
            <span>
              <Button
                variant="outlined"
                size="small"
                startIcon={<AutoAwesomeIcon />}
                onClick={openLlmDialog}
                disabled={llmEnabled === false || loading}
              >
                Suggest with LLM
              </Button>
            </span>
          </Tooltip>
          <Button
            variant="outlined"
            size="small"
            startIcon={docBusy ? <CircularProgress size={14} color="inherit" /> : <UploadFileIcon />}
            onClick={() => fileInputRef.current?.click()}
            disabled={docBusy}
          >
            Import from document
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.txt,.md"
            style={{ display: 'none' }}
            onChange={handleDocumentUpload}
          />
          <Box sx={{ flexGrow: 1 }} />
          <Button
            variant="text"
            size="small"
            startIcon={<DownloadIcon />}
            component="a"
            href={prepareExportUrl(datasetId)}
            target="_blank"
            rel="noopener noreferrer"
          >
            Export PREPARE
          </Button>
          <Button
            variant="text"
            size="small"
            startIcon={<DownloadIcon />}
            component="a"
            href={arriveExportUrl(datasetId)}
            target="_blank"
            rel="noopener noreferrer"
          >
            Export ARRIVE
          </Button>
        </Stack>
      </Paper>

      {/* Pending suggestions panel */}
      {pendingSuggestions.length > 0 && (
        <Card sx={{ mb: 2, border: '1px solid #0288d1' }}>
          <CardContent sx={{ pb: 1 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <LightbulbIcon color="info" />
                <Typography variant="h6">
                  Pending suggestions ({pendingSuggestions.length})
                </Typography>
              </Box>
              <IconButton size="small" onClick={() => setSuggestionsOpen((o) => !o)}>
                {suggestionsOpen ? <ExpandLessIcon /> : <ExpandMoreIcon />}
              </IconButton>
            </Box>
            <Collapse in={suggestionsOpen}>
              <Stack spacing={1} sx={{ mt: 1.5 }}>
                {pendingSuggestions.map((s) => {
                  const field = fieldsById.get(s.field_id)
                  return (
                    <Paper key={s._id} variant="outlined" sx={{ p: 1.5 }}>
                      <Grid container spacing={1.5} alignItems="flex-start">
                        <Grid item xs={12} md={4}>
                          <Typography variant="subtitle2" fontWeight={700}>
                            {field?.label ?? s.field_id}
                          </Typography>
                          <Typography
                            variant="caption"
                            color="text.secondary"
                            sx={{ display: 'block', fontFamily: 'monospace' }}
                          >
                            {s.field_id}
                          </Typography>
                          <Box sx={{ mt: 0.5, display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
                            <Chip
                              label={s.source === 'llm' ? 'LLM' : 'Document'}
                              size="small"
                              color={s.source === 'llm' ? 'secondary' : 'default'}
                            />
                            <Chip
                              label={`conf ${Math.round(s.confidence * 100)}%`}
                              size="small"
                              variant="outlined"
                            />
                          </Box>
                        </Grid>
                        <Grid item xs={12} md={5}>
                          <Typography variant="caption" color="text.secondary">
                            Suggested value
                          </Typography>
                          <Typography
                            variant="body2"
                            sx={{
                              whiteSpace: 'pre-wrap',
                              fontStyle: s.value ? 'normal' : 'italic',
                              wordBreak: 'break-word',
                            }}
                          >
                            {s.value || '(empty)'}
                          </Typography>
                          {s.rationale && (
                            <Typography
                              variant="caption"
                              color="text.secondary"
                              sx={{ display: 'block', mt: 0.5 }}
                            >
                              {s.rationale}
                            </Typography>
                          )}
                        </Grid>
                        <Grid item xs={12} md={3}>
                          <Stack direction="row" spacing={0.5} justifyContent="flex-end">
                            <Button
                              size="small"
                              variant="contained"
                              onClick={() => acceptSuggestion(s)}
                              disabled={!s.value}
                            >
                              Accept
                            </Button>
                            <Button
                              size="small"
                              variant="outlined"
                              onClick={() => editSuggestion(s)}
                            >
                              Edit
                            </Button>
                            <Button
                              size="small"
                              color="error"
                              variant="text"
                              onClick={() => rejectSuggestion(s)}
                            >
                              Reject
                            </Button>
                          </Stack>
                        </Grid>
                      </Grid>
                    </Paper>
                  )
                })}
              </Stack>
            </Collapse>
          </CardContent>
        </Card>
      )}

      {/* Field Table */}
      <Card sx={{ mb: 3, maxWidth: '100%', overflow: 'hidden' }}>
        <CardContent sx={{ minWidth: 0 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2, flexWrap: 'wrap', gap: 1 }}>
            <Typography variant="h6">Fields ({sortedFields.length})</Typography>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              <FormControl size="small" sx={{ minWidth: 140 }}>
                <InputLabel>Filter</InputLabel>
                <Select
                  label="Filter"
                  value={statusFilter}
                  onChange={(e) =>
                    setStatusFilter(e.target.value as typeof statusFilter)
                  }
                >
                  <MenuItem value="all">All</MenuItem>
                  <MenuItem value="missing">Missing</MenuItem>
                  <MenuItem value="partial">Partial</MenuItem>
                  <MenuItem value="satisfied">Satisfied</MenuItem>
                </Select>
              </FormControl>
              <FormControl size="small" sx={{ minWidth: 140 }}>
                <InputLabel>Sort by</InputLabel>
                <Select
                  label="Sort by"
                  value={sortKey}
                  onChange={(e) => setSortKey(e.target.value as SortKey)}
                >
                  <MenuItem value="section">Section</MenuItem>
                  <MenuItem value="severity">Severity</MenuItem>
                  <MenuItem value="status">Status</MenuItem>
                </Select>
              </FormControl>
            </Stack>
          </Box>
          {sortedFields.length === 0 ? (
            <Alert severity="success">No fields match this filter.</Alert>
          ) : (
            <TableContainer component={Paper} variant="outlined" sx={{ width: '100%', overflowX: 'hidden' }}>
              <Table size="small" sx={{ tableLayout: 'fixed', width: '100%' }}>
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ width: 44 }} />
                    <TableCell sx={{ width: { xs: '40%', md: '34%' } }}>Section</TableCell>
                    <TableCell sx={{ width: 96 }}>Severity</TableCell>
                    <TableCell sx={{ width: { xs: '32%', md: '22%' } }}>Field</TableCell>
                    <TableCell sx={{ display: { xs: 'none', xl: 'table-cell' }, width: '22%' }}>
                      Value
                    </TableCell>
                    <TableCell align="right" sx={{ width: 96 }}>Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {sortedFields.map((f) => {
                    const isCrosswalk = f.via_crosswalk
                    const displayValue = f.value ?? ''
                    const truncated =
                      displayValue.length > 80
                        ? displayValue.slice(0, 80) + '…'
                        : displayValue
                    return (
                      <TableRow
                        key={f.field_id}
                        hover
                        sx={{ cursor: 'pointer' }}
                        onClick={() => openDrawer(f)}
                      >
                        <TableCell sx={{ width: 44 }}>
                          <StatusIcon field={f} />
                        </TableCell>
                        <TableCell sx={{ minWidth: 0, pr: 1 }}>
                          <SectionChips field={f} />
                        </TableCell>
                        <TableCell sx={{ width: 96 }}>
                          <Chip
                            label={f.severity}
                            size="small"
                            color={SEVERITY_COLOR[f.severity]}
                            sx={{ textTransform: 'capitalize' }}
                          />
                        </TableCell>
                        <TableCell sx={{ minWidth: 0 }}>
                          <Typography variant="body2" fontWeight={500} sx={{ overflowWrap: 'anywhere' }}>
                            {f.label}
                          </Typography>
                          <Typography
                            variant="caption"
                            color="text.secondary"
                            sx={{ display: 'block', fontFamily: 'monospace', overflowWrap: 'anywhere' }}
                          >
                            {f.field_id}
                            {f.is_column_field ? ' · column' : ''}
                          </Typography>
                          {isCrosswalk && f.satisfied_by_field && (
                            <Typography
                              variant="caption"
                              color="info.main"
                              sx={{ display: 'block' }}
                            >
                              ↗ via {f.satisfied_by_field}
                            </Typography>
                          )}
                        </TableCell>
                        <TableCell sx={{ display: { xs: 'none', xl: 'table-cell' }, minWidth: 0 }}>
                          {displayValue ? (
                            <Tooltip title={displayValue} placement="top-start">
                              <Typography
                                variant="body2"
                                sx={{
                                  fontStyle: isCrosswalk ? 'italic' : 'normal',
                                  color: isCrosswalk ? 'text.secondary' : 'text.primary',
                                  wordBreak: 'break-word',
                                }}
                              >
                                {truncated}
                              </Typography>
                            </Tooltip>
                          ) : (
                            <Typography variant="caption" color="text.secondary">
                              —
                            </Typography>
                          )}
                        </TableCell>
                        <TableCell align="right" onClick={(e) => e.stopPropagation()} sx={{ width: 96 }}>
                          <Stack direction="row" spacing={0.5} justifyContent="flex-end" flexWrap="wrap" useFlexGap>
                            {f.paper_hint && (
                              <Tooltip title={`Paper hint: ${f.paper_hint}`}>
                                <IconButton
                                  size="small"
                                  color="primary"
                                  onClick={() => useHintForField(f)}
                                >
                                  <TipsAndUpdatesIcon fontSize="small" />
                                </IconButton>
                              </Tooltip>
                            )}
                            <Tooltip
                              title={
                                llmEnabled === false
                                  ? 'LLM disabled'
                                  : 'Get an LLM suggestion'
                              }
                            >
                              <span>
                                <IconButton
                                  size="small"
                                  onClick={() => requestLlmForField(f)}
                                  disabled={
                                    llmEnabled === false ||
                                    rowLlmBusy !== null
                                  }
                                >
                                  {rowLlmBusy === f.field_id ? (
                                    <CircularProgress size={14} />
                                  ) : (
                                    <AutoAwesomeIcon fontSize="small" />
                                  )}
                                </IconButton>
                              </span>
                            </Tooltip>
                          </Stack>
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </CardContent>
      </Card>

      {/* Field Editor Drawer */}
      <Drawer
        anchor="right"
        open={drawerField !== null}
        onClose={closeDrawer}
        PaperProps={{
          sx: {
            top: DRAWER_TOP,
            height: { xs: 'calc(100% - 56px)', sm: 'calc(100% - 64px)' },
            width: { xs: '100%', sm: 460 },
          },
        }}
      >
        {drawerField && (
          <Box sx={{ p: 3, minWidth: 0 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 2, gap: 1 }}>
              <Box sx={{ minWidth: 0 }}>
                <Typography variant="h6" sx={{ overflowWrap: 'anywhere' }}>{drawerField.label}</Typography>
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ fontFamily: 'monospace', overflowWrap: 'anywhere' }}
                >
                  {drawerField.field_id}
                </Typography>
              </Box>
              <IconButton onClick={closeDrawer} size="small">
                <CloseIcon />
              </IconButton>
            </Box>
            <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mb: 2 }}>
              <Chip
                label={drawerField.severity}
                size="small"
                color={SEVERITY_COLOR[drawerField.severity]}
                sx={{ textTransform: 'capitalize' }}
              />
              <Chip
                label={drawerField.status}
                size="small"
                color={STATUS_COLOR[drawerField.status]}
                sx={{ textTransform: 'capitalize' }}
              />
              {drawerField.via_crosswalk && (
                <Chip label="via crosswalk" size="small" sx={{ fontStyle: 'italic' }} />
              )}
            </Box>
            <Box sx={{ mb: 2 }}>
              <SectionChips field={drawerField} />
            </Box>
            {drawerField.prompt && (
              <Alert severity="info" icon={<LightbulbIcon />} sx={{ mb: 2 }}>
                <Typography variant="body2">{drawerField.prompt}</Typography>
              </Alert>
            )}
            {drawerField.paper_hint && (
              <Box sx={{ mb: 2 }}>
                <Typography variant="caption" color="text.secondary">
                  Paper hint
                </Typography>
                <Paper variant="outlined" sx={{ p: 1, mt: 0.5, bgcolor: 'grey.50' }}>
                  <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                    {drawerField.paper_hint}
                  </Typography>
                  <Button
                    size="small"
                    sx={{ mt: 0.5 }}
                    onClick={() => setDrawerValue(drawerField.paper_hint ?? '')}
                  >
                    Use this value
                  </Button>
                </Paper>
              </Box>
            )}
            {drawerField.is_column_field && (
              <Alert severity="warning" sx={{ mb: 2 }}>
                This is a column-level field. Saving here only updates the metadata record; ensure
                a matching column exists in the CSV.
              </Alert>
            )}
            <TextField
              label="Value"
              fullWidth
              multiline
              minRows={3}
              maxRows={12}
              value={drawerValue}
              onChange={(e) => setDrawerValue(e.target.value)}
              sx={{ mb: 2 }}
            />
            <Divider sx={{ mb: 2 }} />
            <Stack direction="row" spacing={1} justifyContent="flex-end">
              <Button onClick={closeDrawer}>Cancel</Button>
              <Button
                variant="contained"
                onClick={handleDrawerSave}
                disabled={drawerSaving}
                startIcon={drawerSaving ? <CircularProgress size={14} color="inherit" /> : undefined}
              >
                Save
              </Button>
            </Stack>
          </Box>
        )}
      </Drawer>

      {/* LLM Dialog */}
      <Dialog
        open={llmDialogOpen}
        onClose={() => setLlmDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Suggest field values with LLM</DialogTitle>
        <DialogContent dividers>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Select the fields you want suggestions for. Suggestions land in a review panel — they
            are not applied automatically.
          </Typography>
          <Stack direction="row" spacing={1} sx={{ mb: 2 }}>
            <Button
              size="small"
              onClick={() =>
                setLlmSelectedFields(
                  new Set(templateCompletion.fields.map((f) => f.field_id)),
                )
              }
            >
              Select all
            </Button>
            <Button
              size="small"
              onClick={() =>
                setLlmSelectedFields(
                  new Set(
                    templateCompletion.fields
                      .filter((f) => f.status !== 'satisfied')
                      .map((f) => f.field_id),
                  ),
                )
              }
            >
              Missing + partial
            </Button>
            <Button size="small" onClick={() => setLlmSelectedFields(new Set())}>
              Clear
            </Button>
          </Stack>
          <Box sx={{ maxHeight: 360, overflow: 'auto' }}>
            <Stack>
              {templateCompletion.fields.map((f) => {
                const checked = llmSelectedFields.has(f.field_id)
                return (
                  <FormControlLabel
                    key={f.field_id}
                    control={
                      <Checkbox
                        size="small"
                        checked={checked}
                        onChange={(e) =>
                          setLlmSelectedFields((prev) => {
                            const next = new Set(prev)
                            if (e.target.checked) next.add(f.field_id)
                            else next.delete(f.field_id)
                            return next
                          })
                        }
                      />
                    }
                    label={
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Typography variant="body2">{f.label}</Typography>
                        <Chip
                          label={f.status}
                          size="small"
                          color={STATUS_COLOR[f.status]}
                          sx={{ textTransform: 'capitalize' }}
                        />
                      </Box>
                    }
                  />
                )
              })}
            </Stack>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setLlmDialogOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={handleLlmRun}
            disabled={llmBusy || llmSelectedFields.size === 0}
            startIcon={llmBusy ? <CircularProgress size={14} color="inherit" /> : <AutoAwesomeIcon />}
          >
            Run LLM ({llmSelectedFields.size})
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={toast !== null}
        autoHideDuration={4000}
        onClose={() => setToast(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert severity="success" onClose={() => setToast(null)}>
          {toast}
        </Alert>
      </Snackbar>
    </Box>
  )
}
