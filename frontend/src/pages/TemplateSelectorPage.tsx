import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import CloseIcon from '@mui/icons-material/Close'
import UploadFileIcon from '@mui/icons-material/UploadFile'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControl,
  FormControlLabel,
  Grid,
  IconButton,
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
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  assignTemplate,
  getProfile,
  getTemplate,
  getTemplateSuggestions,
  getTemplateValidation,
  listTemplates,
  unassignTemplate,
  uploadTemplate,
  importLinkmlTemplate,
} from '../api/client'
import { useStore } from '../store/useStore'
import type {
  ConformanceEntry,
  TemplateCandidate,
  TemplateSummary,
} from '../store/useStore'

const STATUS_COLOR: Record<ConformanceEntry['status'], 'success' | 'warning' | 'error'> = {
  satisfied: 'success',
  partial: 'warning',
  missing: 'error',
}

function StatusChip({ status }: { status: ConformanceEntry['status'] }) {
  return <Chip label={status} size="small" color={STATUS_COLOR[status]} sx={{ textTransform: 'capitalize' }} />
}

function ScoreBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100)
  const color: 'success' | 'warning' | 'default' =
    pct >= 75 ? 'success' : pct >= 50 ? 'warning' : 'default'
  return <Chip label={`${pct}%`} size="small" color={color} />
}

function groupConformance(entries: ConformanceEntry[]) {
  const out: Record<string, Record<string, ConformanceEntry[]>> = {}
  for (const e of entries) {
    if (!out[e.standard]) out[e.standard] = {}
    if (!out[e.standard][e.section]) out[e.standard][e.section] = []
    out[e.standard][e.section].push(e)
  }
  return out
}

export default function TemplateSelectorPage() {
  const navigate = useNavigate()
  const {
    datasetId,
    templateId,
    templateCandidates,
    templateConformance,
    availableTemplates,
    setTemplateId,
    setTemplateCandidates,
    setTemplateConformance,
    setAvailableTemplates,
    setColumns,
    setIssues,
  } = useStore()

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewTemplate, setPreviewTemplate] = useState<any>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [uploadBody, setUploadBody] = useState('')
  const [uploadFormat, setUploadFormat] = useState<'yaml' | 'json'>('yaml')
  const [uploadBusy, setUploadBusy] = useState(false)
  const [linkmlBody, setLinkmlBody] = useState('')
  const [linkmlTarget, setLinkmlTarget] = useState('')
  const [linkmlSave, setLinkmlSave] = useState(false)
  const [linkmlBusy, setLinkmlBusy] = useState(false)
  const [linkmlPreview, setLinkmlPreview] = useState<string | null>(null)

  const refreshAll = async () => {
    if (!datasetId) {
      try {
        const list = await listTemplates()
        setAvailableTemplates(list)
      } catch {
        setError('Failed to load templates.')
      }
      return
    }
    setLoading(true)
    setError(null)
    try {
      const [list, suggestions, validation] = await Promise.all([
        listTemplates(),
        getTemplateSuggestions(datasetId).catch(() => ({ candidates: [], auto_assigned: null })),
        getTemplateValidation(datasetId).catch(() => ({ template_id: null, conformance_report: [] })),
      ])
      setAvailableTemplates(list)
      setTemplateCandidates(suggestions.candidates ?? [])
      setTemplateId(validation.template_id ?? null)
      setTemplateConformance(validation.conformance_report ?? [])
    } catch {
      setError('Failed to load template data.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refreshAll()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetId])

  const refreshProfileAfterAssign = async () => {
    if (!datasetId) return
    try {
      const profile = await getProfile(datasetId)
      setColumns(profile.columns)
    } catch {
      // non-fatal
    }
  }

  const handleApply = async (tid: string) => {
    if (!datasetId) return
    setLoading(true)
    setError(null)
    try {
      const result = await assignTemplate(datasetId, tid)
      setTemplateId(result.template_id)
      setTemplateConformance(result.conformance_report ?? [])
      await refreshProfileAfterAssign()
      // refresh issues so the IssueCard reflects template_compliance entries
      try {
        const profile = await getProfile(datasetId)
        setColumns(profile.columns)
      } catch {}
      const list = await listTemplates().catch(() => availableTemplates)
      setAvailableTemplates(list)
      setToast('Template applied.')
    } catch {
      setError('Failed to apply template.')
    } finally {
      setLoading(false)
    }
  }

  const handleUnassign = async () => {
    if (!datasetId) return
    setLoading(true)
    setError(null)
    try {
      await unassignTemplate(datasetId)
      setTemplateId(null)
      setTemplateConformance([])
      await refreshProfileAfterAssign()
      setToast('Template removed.')
    } catch {
      setError('Failed to remove template.')
    } finally {
      setLoading(false)
    }
  }

  const openPreview = async (tid: string) => {
    setPreviewOpen(true)
    setPreviewLoading(true)
    setPreviewTemplate(null)
    try {
      const tpl = await getTemplate(tid)
      setPreviewTemplate(tpl)
    } catch {
      setPreviewTemplate({ error: 'Failed to load template.' })
    } finally {
      setPreviewLoading(false)
    }
  }

  const handleUpload = async () => {
    if (!uploadBody.trim()) {
      setError('Paste template content first.')
      return
    }
    setUploadBusy(true)
    setError(null)
    try {
      await uploadTemplate(uploadBody, uploadFormat)
      const list = await listTemplates()
      setAvailableTemplates(list)
      setUploadBody('')
      setToast('Template uploaded.')
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Template upload failed.')
    } finally {
      setUploadBusy(false)
    }
  }

  const handleImportLinkml = async () => {
    if (!linkmlBody.trim()) {
      setError('Paste a LinkML schema first.')
      return
    }
    setLinkmlBusy(true)
    setError(null)
    setLinkmlPreview(null)
    try {
      const result = await importLinkmlTemplate(
        linkmlBody,
        linkmlTarget.trim() || null,
        linkmlSave,
      )
      setLinkmlPreview(result.as_yaml ?? '')
      if (linkmlSave) {
        const list = await listTemplates()
        setAvailableTemplates(list)
        setToast('LinkML schema imported and saved as user template.')
      } else {
        setToast('LinkML schema converted — review the preview below.')
      }
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'LinkML import failed.')
    } finally {
      setLinkmlBusy(false)
    }
  }

  const handleSaveImported = async () => {
    if (!linkmlPreview) return
    setLinkmlBusy(true)
    setError(null)
    try {
      await uploadTemplate(linkmlPreview, 'yaml')
      const list = await listTemplates()
      setAvailableTemplates(list)
      setLinkmlPreview(null)
      setLinkmlBody('')
      setLinkmlTarget('')
      setToast('Imported template saved.')
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Failed to save imported template.')
    } finally {
      setLinkmlBusy(false)
    }
  }

  const activeTemplate = (() => {
    if (!templateId) return null
    const all = [...availableTemplates.builtin, ...availableTemplates.user]
    return all.find((t) => t.id === templateId) ?? null
  })()

  const candidateById = (tid: string): TemplateCandidate | undefined =>
    templateCandidates.find((c) => c.id === tid)

  const grouped = groupConformance(templateConformance)

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 3 }}>
        <Box>
          <Typography variant="h5">Standards Templates</Typography>
          <Typography variant="body2" color="text.secondary">
            Match your dataset against reporting standards (MNMS, ARRIVE, etc.) to surface missing
            metadata before export.
          </Typography>
        </Box>
        {!datasetId && (
          <Button variant="outlined" onClick={() => navigate('/')}>
            Upload a dataset
          </Button>
        )}
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {loading && (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 2 }}>
          <CircularProgress size={18} />
          <Typography variant="body2" color="text.secondary">
            Loading templates…
          </Typography>
        </Box>
      )}

      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Active Template
          </Typography>
          {activeTemplate ? (
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <Box>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                  <CheckCircleIcon color="success" fontSize="small" />
                  <Typography variant="subtitle1" fontWeight={700}>
                    {activeTemplate.name}
                  </Typography>
                  <Chip label={`v${activeTemplate.version}`} size="small" variant="outlined" />
                  <Chip label={activeTemplate.source} size="small" variant="outlined" />
                </Box>
                {activeTemplate.description && (
                  <Typography variant="body2" color="text.secondary">
                    {activeTemplate.description}
                  </Typography>
                )}
                {activeTemplate.conforms_to.length > 0 && (
                  <Box sx={{ mt: 1, display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
                    {activeTemplate.conforms_to.map((c) => (
                      <Chip key={c} label={c} size="small" />
                    ))}
                  </Box>
                )}
              </Box>
              <Button color="error" variant="outlined" onClick={handleUnassign} disabled={loading}>
                Remove
              </Button>
            </Box>
          ) : (
            <Alert severity="info">No template assigned.</Alert>
          )}
        </CardContent>
      </Card>

      {datasetId && (
        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Suggested Templates
            </Typography>
            {templateCandidates.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                No template suggestions for this dataset.
              </Typography>
            ) : (
              <Stack spacing={1.5}>
                {[...templateCandidates]
                  .sort((a, b) => b.score - a.score)
                  .map((cand) => (
                    <Paper key={cand.id} variant="outlined" sx={{ p: 2 }}>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 2 }}>
                        <Box sx={{ flex: 1 }}>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                            <Typography variant="subtitle2" fontWeight={700}>
                              {cand.name}
                            </Typography>
                            <ScoreBadge score={cand.score} />
                          </Box>
                          {cand.reasons.length > 0 && (
                            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                              {cand.reasons.map((r, i) => (
                                <Chip key={i} label={r} size="small" variant="outlined" />
                              ))}
                            </Box>
                          )}
                        </Box>
                        <Stack direction="row" spacing={1}>
                          <Button size="small" variant="outlined" onClick={() => openPreview(cand.id)}>
                            Preview
                          </Button>
                          <Button
                            size="small"
                            variant="contained"
                            onClick={() => handleApply(cand.id)}
                            disabled={loading || templateId === cand.id}
                          >
                            {templateId === cand.id ? 'Applied' : 'Apply'}
                          </Button>
                        </Stack>
                      </Box>
                    </Paper>
                  ))}
              </Stack>
            )}
          </CardContent>
        </Card>
      )}

      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Browse All Templates
          </Typography>
          <Grid container spacing={3}>
            <Grid item xs={12} md={6}>
              <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                BUILT-IN
              </Typography>
              {availableTemplates.builtin.length === 0 ? (
                <Typography variant="body2" color="text.secondary">
                  None available.
                </Typography>
              ) : (
                <Stack spacing={1.5}>
                  {availableTemplates.builtin.map((tpl) => (
                    <TemplateRow
                      key={tpl.id}
                      tpl={tpl}
                      candidate={candidateById(tpl.id)}
                      isActive={templateId === tpl.id}
                      canApply={!!datasetId}
                      onApply={() => handleApply(tpl.id)}
                      onPreview={() => openPreview(tpl.id)}
                      busy={loading}
                    />
                  ))}
                </Stack>
              )}
            </Grid>
            <Grid item xs={12} md={6}>
              <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                USER-UPLOADED
              </Typography>
              {availableTemplates.user.length === 0 ? (
                <Typography variant="body2" color="text.secondary">
                  No user templates yet. Upload one below.
                </Typography>
              ) : (
                <Stack spacing={1.5}>
                  {availableTemplates.user.map((tpl) => (
                    <TemplateRow
                      key={tpl.id}
                      tpl={tpl}
                      candidate={candidateById(tpl.id)}
                      isActive={templateId === tpl.id}
                      canApply={!!datasetId}
                      onApply={() => handleApply(tpl.id)}
                      onPreview={() => openPreview(tpl.id)}
                      busy={loading}
                    />
                  ))}
                </Stack>
              )}
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Upload Custom Template
          </Typography>
          <Stack spacing={2}>
            <FormControl size="small" sx={{ width: 140 }}>
              <InputLabel>Format</InputLabel>
              <Select
                label="Format"
                value={uploadFormat}
                onChange={(e) => setUploadFormat(e.target.value as 'yaml' | 'json')}
              >
                <MenuItem value="yaml">YAML</MenuItem>
                <MenuItem value="json">JSON</MenuItem>
              </Select>
            </FormControl>
            <TextField
              multiline
              minRows={6}
              maxRows={20}
              fullWidth
              size="small"
              placeholder={
                uploadFormat === 'yaml'
                  ? 'id: my-template\nname: My Template\nversion: 1.0\nconforms_to: []\n...'
                  : '{\n  "id": "my-template",\n  "name": "My Template",\n  "version": "1.0"\n}'
              }
              value={uploadBody}
              onChange={(e) => setUploadBody(e.target.value)}
              sx={{ fontFamily: 'monospace' }}
            />
            <Box>
              <Button
                variant="contained"
                startIcon={uploadBusy ? <CircularProgress size={16} color="inherit" /> : <UploadFileIcon />}
                onClick={handleUpload}
                disabled={uploadBusy}
              >
                Upload Template
              </Button>
            </Box>
          </Stack>
        </CardContent>
      </Card>

      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Import from LinkML Schema
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Paste a LinkML schema YAML (e.g. NAMO at{' '}
            <a
              href="https://raw.githubusercontent.com/monarch-initiative/namo/main/src/namo/schema/namo.yaml"
              target="_blank"
              rel="noopener noreferrer"
            >
              monarch-initiative/namo
            </a>
            ) and the converter will produce a starter FAIR-VCG template. Leave the target class
            empty to extract dataset-level metadata from all data-like classes, or specify a class
            (e.g. <code>FunctionalAssay</code>, <code>DoseResponseSimilarity</code>) to produce
            required_columns from its attributes.
          </Typography>
          <Stack spacing={2}>
            <TextField
              multiline
              minRows={6}
              maxRows={20}
              fullWidth
              size="small"
              placeholder={'id: https://example.org/my-schema\nname: my-schema\nclasses:\n  Foo:\n    attributes:\n      bar:\n        range: float'}
              value={linkmlBody}
              onChange={(e) => setLinkmlBody(e.target.value)}
              sx={{ fontFamily: 'monospace' }}
            />
            <Box sx={{ display: 'flex', gap: 2, alignItems: 'center', flexWrap: 'wrap' }}>
              <TextField
                size="small"
                label="Target class (optional)"
                value={linkmlTarget}
                onChange={(e) => setLinkmlTarget(e.target.value)}
                placeholder="FunctionalAssay"
                sx={{ width: 280 }}
              />
              <FormControlLabel
                control={
                  <Checkbox
                    checked={linkmlSave}
                    onChange={(e) => setLinkmlSave(e.target.checked)}
                  />
                }
                label="Save as user template"
              />
              <Button
                variant="contained"
                onClick={handleImportLinkml}
                disabled={linkmlBusy}
                startIcon={linkmlBusy ? <CircularProgress size={16} color="inherit" /> : <UploadFileIcon />}
              >
                Convert
              </Button>
            </Box>
            {linkmlPreview && (
              <Box>
                <Typography variant="subtitle2" sx={{ mb: 1 }}>
                  Generated template preview
                </Typography>
                <Box
                  component="pre"
                  sx={{
                    p: 2,
                    bgcolor: 'grey.100',
                    borderRadius: 1,
                    fontSize: 12,
                    maxHeight: 360,
                    overflow: 'auto',
                    whiteSpace: 'pre-wrap',
                  }}
                >
                  {linkmlPreview}
                </Box>
                {!linkmlSave && (
                  <Button
                    variant="outlined"
                    size="small"
                    sx={{ mt: 1 }}
                    onClick={handleSaveImported}
                    disabled={linkmlBusy}
                  >
                    Save now
                  </Button>
                )}
              </Box>
            )}
          </Stack>
        </CardContent>
      </Card>

      {datasetId && (
        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Conformance Report
            </Typography>
            {!templateId ? (
              <Alert severity="info">Assign a template to see a conformance report.</Alert>
            ) : templateConformance.length === 0 ? (
              <Alert severity="success">No conformance issues against this template.</Alert>
            ) : (
              Object.entries(grouped).map(([standard, sections]) => (
                <Box key={standard} sx={{ mb: 2 }}>
                  <Typography variant="subtitle1" fontWeight={700} sx={{ mb: 1 }}>
                    {standard}
                  </Typography>
                  {Object.entries(sections).map(([section, entries]) => (
                    <Box key={section} sx={{ mb: 2 }}>
                      <Typography
                        variant="caption"
                        color="text.secondary"
                        sx={{ textTransform: 'uppercase', letterSpacing: 0.5, display: 'block', mb: 0.5 }}
                      >
                        {section}
                      </Typography>
                      <TableContainer component={Paper} variant="outlined">
                        <Table size="small">
                          <TableHead>
                            <TableRow>
                              <TableCell>Field</TableCell>
                              <TableCell>Status</TableCell>
                              <TableCell>Satisfied by</TableCell>
                              <TableCell>Severity</TableCell>
                            </TableRow>
                          </TableHead>
                          <TableBody>
                            {entries.map((e) => (
                              <TableRow key={`${e.standard}-${e.section}-${e.field_id}`}>
                                <TableCell>
                                  <Typography variant="body2" fontWeight={500}>
                                    {e.field_id}
                                  </Typography>
                                  <Typography variant="caption" color="text.secondary">
                                    {e.is_column_field ? 'column field' : 'dataset field'}
                                  </Typography>
                                </TableCell>
                                <TableCell>
                                  <StatusChip status={e.status} />
                                </TableCell>
                                <TableCell>
                                  {e.satisfied_by ? (
                                    e.satisfied_by.column ? (
                                      <Chip label={`column: ${e.satisfied_by.column}`} size="small" />
                                    ) : e.satisfied_by.metadata ? (
                                      <Chip label={`metadata: ${e.satisfied_by.metadata}`} size="small" />
                                    ) : (
                                      <Typography variant="caption" color="text.secondary">
                                        —
                                      </Typography>
                                    )
                                  ) : (
                                    <Typography variant="caption" color="text.secondary">
                                      —
                                    </Typography>
                                  )}
                                </TableCell>
                                <TableCell>
                                  <Chip
                                    label={e.severity}
                                    size="small"
                                    color={
                                      e.severity === 'high'
                                        ? 'error'
                                        : e.severity === 'medium'
                                          ? 'warning'
                                          : 'default'
                                    }
                                  />
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </TableContainer>
                    </Box>
                  ))}
                  <Divider sx={{ my: 1 }} />
                </Box>
              ))
            )}
          </CardContent>
        </Card>
      )}

      <Dialog open={previewOpen} onClose={() => setPreviewOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          Template Preview
          <IconButton onClick={() => setPreviewOpen(false)} size="small">
            <CloseIcon />
          </IconButton>
        </DialogTitle>
        <DialogContent dividers>
          {previewLoading ? (
            <Box sx={{ textAlign: 'center', py: 4 }}>
              <CircularProgress />
            </Box>
          ) : (
            <Box
              component="pre"
              sx={{
                fontFamily: 'monospace',
                fontSize: 12,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                m: 0,
              }}
            >
              {previewTemplate ? JSON.stringify(previewTemplate, null, 2) : ''}
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPreviewOpen(false)}>Close</Button>
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

function TemplateRow({
  tpl,
  candidate,
  isActive,
  canApply,
  onApply,
  onPreview,
  busy,
}: {
  tpl: TemplateSummary
  candidate: TemplateCandidate | undefined
  isActive: boolean
  canApply: boolean
  onApply: () => void
  onPreview: () => void
  busy: boolean
}) {
  return (
    <Paper variant="outlined" sx={{ p: 1.5 }}>
      <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 1 }}>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
            <Typography variant="subtitle2" fontWeight={700}>
              {tpl.name}
            </Typography>
            <Chip label={`v${tpl.version}`} size="small" variant="outlined" />
            {candidate && <ScoreBadge score={candidate.score} />}
            {isActive && <Chip label="active" size="small" color="success" />}
          </Box>
          {tpl.description && (
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
              {tpl.description}
            </Typography>
          )}
        </Box>
        <Stack direction="row" spacing={1}>
          <Button size="small" variant="outlined" onClick={onPreview}>
            Preview
          </Button>
          <Button
            size="small"
            variant="contained"
            onClick={onApply}
            disabled={busy || isActive || !canApply}
          >
            {isActive ? 'Active' : 'Apply'}
          </Button>
        </Stack>
      </Box>
    </Paper>
  )
}
