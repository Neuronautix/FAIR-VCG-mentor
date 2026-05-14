import BookmarkAddIcon from '@mui/icons-material/BookmarkAdd'
import SaveIcon from '@mui/icons-material/Save'
import WarningAmberIcon from '@mui/icons-material/WarningAmber'
import {
  Alert,
  AlertTitle,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  FormControl,
  Grid,
  InputLabel,
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
  TablePagination,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  getProfile,
  listHITLSuggestions,
  requestLLMColumnSuggestions,
  saveTemplate,
  updateColumns,
} from '../api/client'
import HITLPanel from '../components/HITLPanel'
import { useStore } from '../store/useStore'
import type { ColumnProfile } from '../store/useStore'

const SEMANTIC_TYPES = [
  'identifier',
  'biological_descriptor',
  'experimental_condition',
  'measurement',
  'time_variable',
  'free_text_note',
  'metadata_field',
  'categorical',
  'unknown',
]

const DATA_TYPES = ['string', 'number', 'integer', 'categorical', 'date', 'boolean']

const TYPE_COLORS: Record<string, string> = {
  identifier: '#7b1fa2',
  biological_descriptor: '#1565c0',
  experimental_condition: '#00695c',
  measurement: '#e65100',
  time_variable: '#c62828',
  free_text_note: '#795548',
  metadata_field: '#546e7a',
  categorical: '#0288d1',
  unknown: '#9e9e9e',
}

function ColumnEditor({
  col,
  onChange,
}: {
  col: ColumnProfile
  onChange: (updated: ColumnProfile) => void
}) {
  return (
    <Grid container spacing={1.5}>
      <Grid item xs={12} sm={6} md={3}>
        <TextField
          label="Label"
          size="small"
          fullWidth
          value={col.user_label ?? col.label ?? col.name}
          onChange={(e) => onChange({ ...col, user_label: e.target.value })}
        />
      </Grid>
      <Grid item xs={12} sm={6} md={3}>
        <TextField
          label="Description"
          size="small"
          fullWidth
          value={col.user_description ?? ''}
          onChange={(e) => onChange({ ...col, user_description: e.target.value })}
        />
      </Grid>
      <Grid item xs={6} sm={4} md={2}>
        <FormControl size="small" fullWidth>
          <InputLabel>Semantic type</InputLabel>
          <Select
            label="Semantic type"
            value={col.user_type ?? col.inferred_type}
            onChange={(e) => onChange({ ...col, user_type: e.target.value })}
          >
            {SEMANTIC_TYPES.map((t) => (
              <MenuItem key={t} value={t}>
                {t.replace(/_/g, ' ')}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </Grid>
      <Grid item xs={6} sm={4} md={2}>
        <FormControl size="small" fullWidth>
          <InputLabel>Data type</InputLabel>
          <Select
            label="Data type"
            value={col.data_type}
            onChange={(e) => onChange({ ...col, data_type: e.target.value })}
          >
            {DATA_TYPES.map((t) => (
              <MenuItem key={t} value={t}>
                {t}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </Grid>
      <Grid item xs={6} sm={4} md={1}>
        <TextField
          label="Unit"
          size="small"
          fullWidth
          value={col.user_unit ?? ''}
          onChange={(e) => onChange({ ...col, user_unit: e.target.value })}
          placeholder={col.unit_guess ?? ''}
        />
      </Grid>
      <Grid item xs={6} sm={6} md={1}>
        <TextField
          label="Allowed values"
          size="small"
          fullWidth
          value={col.allowed_values?.join('|') ?? ''}
          onChange={(e) =>
            onChange({
              ...col,
              allowed_values: e.target.value ? e.target.value.split('|').map((v) => v.trim()) : null,
            })
          }
          placeholder="a|b|c"
        />
      </Grid>
    </Grid>
  )
}

export default function ColumnProfilePage() {
  const navigate = useNavigate()
  const {
    datasetId,
    columns,
    lowConfidenceColumns,
    templateApplied,
    setColumns,
    setIssues,
    setFairScore,
    setLowConfidenceColumns,
    setInferenceMetrics,
    paperExtraction,
    llmEnabled,
    setHITLSuggestions,
  } = useStore()
  const [llmRequesting, setLlmRequesting] = useState(false)
  const [localCols, setLocalCols] = useState<ColumnProfile[]>(columns)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [savingTemplate, setSavingTemplate] = useState(false)
  const [templateMessage, setTemplateMessage] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(25)
  const [paperHintDismissed, setPaperHintDismissed] = useState(false)

  if (!datasetId) {
    return <Alert severity="info">No dataset loaded. Please upload a CSV first.</Alert>
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const result = await updateColumns(datasetId, localCols)
      setColumns(result.columns)
      setIssues(result.issues)
      setFairScore(null)
      setLocalCols(result.columns)
      if (result.low_confidence_columns) {
        setLowConfidenceColumns(result.low_confidence_columns)
      }
      if (result.inference_metrics) {
        setInferenceMetrics(result.inference_metrics)
      }
      setSaved(true)
    } finally {
      setSaving(false)
    }
  }

  const handleRequestLLM = async () => {
    if (!datasetId) return
    setLlmRequesting(true)
    try {
      const targets = lowConfidenceColumns.length
        ? lowConfidenceColumns.map((c) => c.name)
        : undefined
      await requestLLMColumnSuggestions(datasetId, targets)
      const fresh = await listHITLSuggestions(datasetId)
      setHITLSuggestions(fresh)
    } finally {
      setLlmRequesting(false)
    }
  }

  const refreshColumns = async () => {
    if (!datasetId) return
    const fresh = await getProfile(datasetId)
    setColumns(fresh.columns)
    setLocalCols(fresh.columns)
    setFairScore(null)
  }

  const handleSaveTemplate = async () => {
    setSavingTemplate(true)
    try {
      const result = await saveTemplate(datasetId)
      setTemplateMessage(`Template saved (${result.n_columns} columns).`)
    } catch {
      setTemplateMessage('Could not save template.')
    } finally {
      setSavingTemplate(false)
    }
  }

  const lowConfidenceNames = new Set(lowConfidenceColumns.map((c) => c.name))

  const paperOutcomeSet = new Set(paperExtraction?.vcg_hints.outcome_columns ?? [])
  const paperCovariateSet = new Set(paperExtraction?.vcg_hints.covariate_columns ?? [])
  const paperMatchCount = localCols.filter(
    (c) => paperOutcomeSet.has(c.name) || paperCovariateSet.has(c.name)
  ).length
  const showPaperHintBanner =
    !paperHintDismissed &&
    paperExtraction != null &&
    paperMatchCount > 0

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h5">Column Profile</Typography>
        <Stack direction="row" spacing={1.5}>
          <Button
            variant="outlined"
            startIcon={savingTemplate ? <CircularProgress size={16} /> : <BookmarkAddIcon />}
            onClick={handleSaveTemplate}
            disabled={savingTemplate}
          >
            Save as template
          </Button>
          <Button
            variant="contained"
            startIcon={saving ? <CircularProgress size={16} color="inherit" /> : <SaveIcon />}
            onClick={handleSave}
            disabled={saving}
          >
            Save changes
          </Button>
        </Stack>
      </Box>

      {templateApplied > 0 && (
        <Alert severity="success" sx={{ mb: 2 }}>
          Re-applied a saved template to {templateApplied} column
          {templateApplied === 1 ? '' : 's'} for this dataset signature.
        </Alert>
      )}

      {lowConfidenceColumns.length > 0 && (
        <Alert
          severity="warning"
          icon={<WarningAmberIcon />}
          sx={{ mb: 2 }}
        >
          <AlertTitle>
            {lowConfidenceColumns.length} column{lowConfidenceColumns.length === 1 ? '' : 's'} need review
          </AlertTitle>
          The automatic classifier was not confident about these columns
          (confidence &lt; 0.65). Please review and correct them, then click
          <strong> Save as template</strong> so future uploads of the same
          dataset shape are configured automatically.
          <Box sx={{ mt: 1, display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
            {lowConfidenceColumns.slice(0, 12).map((c) => (
              <Chip
                key={c.name}
                size="small"
                label={`${c.name} · ${c.inferred_type} · ${(c.confidence * 100).toFixed(0)}%`}
                onClick={() => setExpanded(c.name)}
                sx={{ cursor: 'pointer' }}
              />
            ))}
            {lowConfidenceColumns.length > 12 && (
              <Chip size="small" label={`+${lowConfidenceColumns.length - 12} more`} />
            )}
          </Box>
        </Alert>
      )}

      <Alert severity="info" sx={{ mb: 2 }}>
        Review and correct the automatic column classification below. Descriptions and units are used
        to generate the data dictionary, CSVW, and JSON-LD exports.
      </Alert>

      <HITLPanel
        category="column_metadata"
        title="AI column suggestions — Human review required"
        emptyHint={
          llmEnabled === false
            ? 'Claude Haiku is disabled on the server. Set ANTHROPIC_API_KEY to enable.'
            : 'Click "Ask Claude Haiku" to get metadata suggestions for low-confidence columns. Every suggestion is shown here for you to approve, edit, or reject.'
        }
        refreshAction={{
          label: lowConfidenceColumns.length
            ? `Ask Claude Haiku (${lowConfidenceColumns.length})`
            : 'Ask Claude Haiku',
          onClick: handleRequestLLM,
          pending: llmRequesting,
        }}
        onApplied={() => {
          refreshColumns()
        }}
      />

      {showPaperHintBanner && (
        <Alert
          severity="info"
          sx={{ mb: 2 }}
          onClose={() => setPaperHintDismissed(true)}
        >
          {paperMatchCount} column{paperMatchCount === 1 ? '' : 's'} match paper hints from "
          {paperExtraction!._filename}". Highlighted below.
        </Alert>
      )}

      {/* Summary table */}
      <Card sx={{ mb: 3 }}>
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow sx={{ background: '#f5f7fa' }}>
                <TableCell>Column</TableCell>
                <TableCell>Semantic type</TableCell>
                <TableCell>Data type</TableCell>
                <TableCell>Unit</TableCell>
                <TableCell align="right">Unique</TableCell>
                <TableCell align="right">Missing %</TableCell>
                <TableCell>Sample values</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {localCols.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage).map((col) => (
                <TableRow
                  key={col.name}
                  hover
                  selected={expanded === col.name}
                  sx={{
                    cursor: 'pointer',
                    background: lowConfidenceNames.has(col.name) ? 'rgba(237,108,2,0.08)' : undefined,
                  }}
                  onClick={() => setExpanded(expanded === col.name ? null : col.name)}
                >
                  <TableCell>
                    <Typography variant="body2" fontWeight={600}>
                      {col.name}
                    </Typography>
                    {paperOutcomeSet.has(col.name) && (
                      <Chip label="endpoint (paper)" color="warning" size="small" sx={{ mt: 0.5, mr: 0.5 }} />
                    )}
                    {paperCovariateSet.has(col.name) && (
                      <Chip label="covariate (paper)" color="secondary" size="small" sx={{ mt: 0.5 }} />
                    )}
                  </TableCell>
                  <TableCell>
                    <Chip
                      label={(col.user_type ?? col.inferred_type).replace(/_/g, ' ')}
                      size="small"
                      sx={{
                        background: (TYPE_COLORS[col.user_type ?? col.inferred_type] ?? '#9e9e9e') + '22',
                        color: TYPE_COLORS[col.user_type ?? col.inferred_type] ?? '#9e9e9e',
                        fontSize: 11,
                      }}
                    />
                  </TableCell>
                  <TableCell>
                    <Typography variant="caption">{col.data_type}</Typography>
                  </TableCell>
                  <TableCell>
                    <Typography variant="caption" color={col.user_unit ? 'text.primary' : 'text.secondary'}>
                      {col.user_unit || col.unit_guess || '—'}
                    </Typography>
                  </TableCell>
                  <TableCell align="right">
                    <Typography variant="caption">{col.unique_values}</Typography>
                  </TableCell>
                  <TableCell align="right">
                    <Typography
                      variant="caption"
                      color={col.missing_pct > 20 ? 'error.main' : 'text.secondary'}
                    >
                      {col.missing_pct}%
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
                      {col.sample_values.slice(0, 3).join(', ')}
                    </Typography>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
        <TablePagination
          component="div"
          count={localCols.length}
          page={page}
          onPageChange={(_, newPage) => {
            setPage(newPage)
            setExpanded(null)
          }}
          rowsPerPage={rowsPerPage}
          onRowsPerPageChange={(e) => {
            setRowsPerPage(parseInt(e.target.value, 10))
            setPage(0)
            setExpanded(null)
          }}
          rowsPerPageOptions={[10, 25, 50]}
        />
      </Card>

      {/* Expanded editor */}
      {expanded && (
        <Paper variant="outlined" sx={{ p: 2, mb: 3, border: '2px solid #1976d2' }}>
          <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 1.5 }}>
            Editing: {expanded}
          </Typography>
          <ColumnEditor
            col={localCols.find((c) => c.name === expanded)!}
            onChange={(updated) =>
              setLocalCols((prev) => prev.map((c) => (c.name === updated.name ? updated : c)))
            }
          />
        </Paper>
      )}

      <Box sx={{ display: 'flex', gap: 2, justifyContent: 'flex-end' }}>
        <Button variant="outlined" onClick={() => navigate('/fair-score')}>
          Skip to FAIR Score
        </Button>
        <Button
          variant="contained"
          onClick={async () => { await handleSave(); navigate('/fair-score') }}
          disabled={saving}
        >
          Save and continue
        </Button>
      </Box>

      <Snackbar open={saved} autoHideDuration={3000} onClose={() => setSaved(false)}>
        <Alert severity="success" onClose={() => setSaved(false)}>
          Column mappings saved.
        </Alert>
      </Snackbar>

      <Snackbar
        open={!!templateMessage}
        autoHideDuration={4000}
        onClose={() => setTemplateMessage(null)}
      >
        <Alert
          severity={templateMessage?.startsWith('Template saved') ? 'success' : 'error'}
          onClose={() => setTemplateMessage(null)}
        >
          {templateMessage}
        </Alert>
      </Snackbar>
    </Box>
  )
}
