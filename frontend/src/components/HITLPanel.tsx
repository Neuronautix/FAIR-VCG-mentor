import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome'
import CheckIcon from '@mui/icons-material/Check'
import CloseIcon from '@mui/icons-material/Close'
import EditIcon from '@mui/icons-material/Edit'
import RefreshIcon from '@mui/icons-material/Refresh'
import ScienceIcon from '@mui/icons-material/Science'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  IconButton,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import { useEffect, useMemo, useState } from 'react'
import {
  approveHITLSuggestion,
  editHITLSuggestion,
  HITLSuggestion,
  listHITLSuggestions,
  rejectHITLSuggestion,
} from '../api/client'
import { useStore } from '../store/useStore'

const CATEGORY_LABELS: Record<HITLSuggestion['category'], string> = {
  column_metadata: 'Column metadata',
  dataset_metadata: 'Dataset metadata',
  vcg_config: 'VCG configuration',
  fair_recommendation: 'FAIR recommendation',
  issue_fix: 'Issue fix',
  schema_extension: 'Schema extension',
}

const STATUS_COLORS: Record<HITLSuggestion['status'], 'default' | 'warning' | 'success' | 'error' | 'info'> = {
  pending: 'warning',
  edited: 'info',
  approved: 'success',
  applied: 'success',
  rejected: 'default',
  invalid: 'error',
  stale: 'default',
}

interface Props {
  category?: HITLSuggestion['category']
  title?: string
  emptyHint?: string
  /** Render an action button at the top to request fresh LLM suggestions */
  refreshAction?: { label: string; onClick: () => Promise<void> | void; pending?: boolean }
  /** Called after any suggestion is applied (so parents can refresh derived state) */
  onApplied?: (suggestion: HITLSuggestion) => void
  /** Show only N most recent + a 'show more' link */
  maxVisible?: number
}

export default function HITLPanel({
  category,
  title,
  emptyHint,
  refreshAction,
  onApplied,
  maxVisible = 6,
}: Props) {
  const { datasetId, hitlSuggestions, setHITLSuggestions, llmEnabled } = useStore()
  const [loading, setLoading] = useState(false)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [expanded, setExpanded] = useState(false)

  const refresh = async () => {
    if (!datasetId) return
    setLoading(true)
    try {
      const data = await listHITLSuggestions(datasetId)
      setHITLSuggestions(data)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetId])

  const filtered = useMemo(() => {
    const list = category
      ? hitlSuggestions.filter((s) => s.category === category)
      : hitlSuggestions
    return [...list].sort((a, b) => {
      const order: Record<HITLSuggestion['status'], number> = {
        pending: 0, edited: 1, invalid: 2, stale: 3, applied: 4, approved: 5, rejected: 6,
      }
      const ds = order[a.status] - order[b.status]
      if (ds !== 0) return ds
      return b.created_at - a.created_at
    })
  }, [hitlSuggestions, category])

  const visible = expanded ? filtered : filtered.slice(0, maxVisible)
  const pendingCount = filtered.filter((s) => s.status === 'pending' || s.status === 'edited').length

  const onApprove = async (s: HITLSuggestion) => {
    if (!datasetId) return
    setBusyId(s.id)
    try {
      const res = await approveHITLSuggestion(datasetId, s.id)
      setHITLSuggestions(hitlSuggestions.map((x) => (x.id === s.id ? res.suggestion : x)))
      onApplied?.(res.suggestion)
    } finally {
      setBusyId(null)
    }
  }

  const onReject = async (s: HITLSuggestion) => {
    if (!datasetId) return
    setBusyId(s.id)
    try {
      const res = await rejectHITLSuggestion(datasetId, s.id)
      setHITLSuggestions(hitlSuggestions.map((x) => (x.id === s.id ? res.suggestion : x)))
    } finally {
      setBusyId(null)
    }
  }

  const onEdit = async (s: HITLSuggestion, payload: Record<string, any>) => {
    if (!datasetId) return
    setBusyId(s.id)
    try {
      const res = await editHITLSuggestion(datasetId, s.id, payload)
      setHITLSuggestions(hitlSuggestions.map((x) => (x.id === s.id ? res.suggestion : x)))
    } finally {
      setBusyId(null)
    }
  }

  if (llmEnabled === false && filtered.length === 0) {
    return null // AI not configured + no rule-based suggestions either
  }

  return (
    <Card variant="outlined" sx={{ mb: 2 }}>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 1.5 }}>
          <AutoAwesomeIcon fontSize="small" sx={{ mr: 1, color: 'primary.main' }} />
          <Typography variant="subtitle1" fontWeight={700} sx={{ flexGrow: 1 }}>
            {title ?? 'AI suggestions (Human review required)'}
          </Typography>
          {pendingCount > 0 && (
            <Chip label={`${pendingCount} pending`} size="small" color="warning" sx={{ mr: 1 }} />
          )}
          <Tooltip title="Refresh">
            <span>
              <IconButton size="small" onClick={refresh} disabled={loading}>
                {loading ? <CircularProgress size={16} /> : <RefreshIcon fontSize="small" />}
              </IconButton>
            </span>
          </Tooltip>
          {refreshAction && (
            <Button
              size="small"
              variant="outlined"
              startIcon={refreshAction.pending ? <CircularProgress size={14} /> : <ScienceIcon />}
              onClick={() => refreshAction.onClick()}
              disabled={refreshAction.pending || llmEnabled === false}
              sx={{ ml: 1 }}
            >
              {refreshAction.label}
            </Button>
          )}
        </Box>

        {llmEnabled === false && (
          <Alert severity="info" sx={{ mb: 1.5 }}>
            Set <code>ANTHROPIC_API_KEY</code> on the backend to enable Claude Haiku-powered suggestions.
          </Alert>
        )}

        {filtered.length === 0 && !loading && (
          <Typography variant="body2" color="text.secondary">
            {emptyHint ?? 'No suggestions yet. Click the action button to ask Claude Haiku.'}
          </Typography>
        )}

        <Stack spacing={1}>
          {visible.map((s) => (
            <SuggestionCard
              key={s.id}
              s={s}
              busy={busyId === s.id}
              onApprove={onApprove}
              onReject={onReject}
              onEdit={onEdit}
            />
          ))}
        </Stack>

        {filtered.length > maxVisible && (
          <Button size="small" sx={{ mt: 1 }} onClick={() => setExpanded((e) => !e)}>
            {expanded ? 'Show less' : `Show all ${filtered.length}`}
          </Button>
        )}
      </CardContent>
    </Card>
  )
}

function SuggestionCard({
  s,
  busy,
  onApprove,
  onReject,
  onEdit,
}: {
  s: HITLSuggestion
  busy: boolean
  onApprove: (s: HITLSuggestion) => void
  onReject: (s: HITLSuggestion) => void
  onEdit: (s: HITLSuggestion, payload: Record<string, any>) => void
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<string>(JSON.stringify(s.payload, null, 2))
  const [editError, setEditError] = useState<string | null>(null)

  const isActionable = s.status === 'pending' || s.status === 'edited'
  const isStale = s.status === 'stale'
  const isAI = s.source.startsWith('llm:')

  return (
    <Card
      variant="outlined"
      sx={{
        bgcolor: isActionable
          ? 'rgba(255, 193, 7, 0.04)'
          : isStale
            ? 'rgba(0, 0, 0, 0.03)'
            : 'transparent',
        opacity: isStale ? 0.65 : 1,
      }}
    >
      <CardContent sx={{ pb: '12px !important' }}>
        <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
          <Box sx={{ flexGrow: 1 }}>
            <Stack direction="row" spacing={0.75} sx={{ mb: 0.5, flexWrap: 'wrap' }}>
              <Chip
                label={CATEGORY_LABELS[s.category]}
                size="small"
                variant="outlined"
                sx={{ fontSize: 10 }}
              />
              <Chip
                label={s.status}
                size="small"
                color={STATUS_COLORS[s.status]}
                sx={{ fontSize: 10 }}
              />
              {isAI && (
                <Chip
                  icon={<AutoAwesomeIcon sx={{ fontSize: 12 }} />}
                  label={`Haiku · ${(s.confidence * 100).toFixed(0)}%`}
                  size="small"
                  variant="outlined"
                  color="primary"
                  sx={{ fontSize: 10 }}
                />
              )}
              {!isAI && (
                <Chip label={s.source} size="small" variant="outlined" sx={{ fontSize: 10 }} />
              )}
              <Chip label={`for: ${s.target}`} size="small" variant="outlined" sx={{ fontSize: 10 }} />
              {typeof (s as any).schema_version === 'number' && (
                <Chip
                  label={`schema v${(s as any).schema_version}`}
                  size="small"
                  variant="outlined"
                  sx={{ fontSize: 10 }}
                />
              )}
            </Stack>

            {isStale && (
              <Alert severity="info" sx={{ mt: 0.5, mb: 0.5, fontSize: 11, py: 0 }}>
                Vocabulary has changed since this suggestion was generated. Re-run the request
                to get fresh proposals.
              </Alert>
            )}

            <Typography variant="body2" fontWeight={600} sx={{ mb: 0.5 }}>
              {s.title}
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
              {s.rationale}
            </Typography>

            {!s.validation.ok && s.validation.errors.length > 0 && (
              <Alert severity="error" sx={{ mt: 1, fontSize: 12, py: 0 }}>
                {s.validation.errors.join(' · ')}
              </Alert>
            )}

            {editing ? (
              <Box sx={{ mt: 1.5 }}>
                <TextField
                  multiline
                  fullWidth
                  minRows={3}
                  size="small"
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  helperText="Edit the JSON payload, then save."
                />
                {editError && (
                  <Alert severity="error" sx={{ mt: 1, fontSize: 12 }}>
                    {editError}
                  </Alert>
                )}
                <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                  <Button
                    size="small"
                    variant="contained"
                    onClick={() => {
                      try {
                        const parsed = JSON.parse(draft)
                        setEditError(null)
                        onEdit(s, parsed)
                        setEditing(false)
                      } catch (e: any) {
                        setEditError(`Invalid JSON: ${e.message}`)
                      }
                    }}
                    disabled={busy}
                  >
                    Save edit
                  </Button>
                  <Button size="small" onClick={() => setEditing(false)}>
                    Cancel
                  </Button>
                </Stack>
              </Box>
            ) : (
              <Box sx={{ mt: 1, fontFamily: 'monospace', fontSize: 11, color: 'text.secondary' }}>
                {Object.entries(s.payload).slice(0, 4).map(([k, v]) => (
                  <Box key={k} sx={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    <strong>{k}:</strong>{' '}
                    {typeof v === 'string' ? v : JSON.stringify(v)}
                  </Box>
                ))}
              </Box>
            )}
          </Box>

          {isActionable && !editing && (
            <Stack direction="column" spacing={0.5}>
              <Tooltip title="Approve and apply">
                <span>
                  <IconButton
                    size="small"
                    color="success"
                    disabled={busy || !s.validation.ok}
                    onClick={() => onApprove(s)}
                  >
                    {busy ? <CircularProgress size={16} /> : <CheckIcon fontSize="small" />}
                  </IconButton>
                </span>
              </Tooltip>
              <Tooltip title="Edit before approving">
                <IconButton size="small" disabled={busy} onClick={() => setEditing(true)}>
                  <EditIcon fontSize="small" />
                </IconButton>
              </Tooltip>
              <Tooltip title="Reject">
                <IconButton size="small" color="error" disabled={busy} onClick={() => onReject(s)}>
                  <CloseIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            </Stack>
          )}
        </Box>
      </CardContent>
    </Card>
  )
}
