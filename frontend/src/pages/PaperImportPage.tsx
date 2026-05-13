import { useCallback, useRef, useState } from 'react'
import ArticleIcon from '@mui/icons-material/Article'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import ErrorIcon from '@mui/icons-material/Error'
import HelpOutlineIcon from '@mui/icons-material/HelpOutline'
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
  List,
  ListItem,
  ListItemText,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material'
import { useNavigate } from 'react-router-dom'
import { extractPaperMetadata, saveMetadata } from '../api/client'
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

export default function PaperImportPage() {
  const navigate = useNavigate()
  const { datasetId, paperExtraction, setPaperExtraction, setMetadata } = useStore()

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [applySuccess, setApplySuccess] = useState(false)
  const [showArrive, setShowArrive] = useState(false)

  const handleFile = async (file: File) => {
    setError(null)
    setApplySuccess(false)
    setLoading(true)
    try {
      const result = await extractPaperMetadata(file)
      setPaperExtraction(result as PaperExtraction)
    } catch (err: any) {
      const msg =
        err?.response?.data?.detail ??
        err?.message ??
        'Extraction failed. Check that ANTHROPIC_API_KEY is configured on the server.'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  const handleApply = async () => {
    if (!paperExtraction || !datasetId) return
    const dm = paperExtraction.dataset_metadata
    const patch: Record<string, any> = {}
    if (dm.title) patch.title = dm.title
    if (dm.description) patch.description = dm.description
    if (dm.creator) patch.creator = dm.creator
    if (dm.institution) patch.institution = dm.institution
    if (dm.species) patch.species = dm.species
    if (dm.study_type) patch.study_type = dm.study_type
    if (dm.keywords?.length) patch.keywords = dm.keywords
    if (dm.license) patch.license = dm.license
    if (dm.funding_source) patch.funding_source = dm.funding_source
    if (dm.protocol_reference) patch.protocol_reference = dm.protocol_reference
    // Store ARRIVE data in metadata for ARRIVE export engine
    patch.arrive = paperExtraction.arrive
    try {
      const saved = await saveMetadata(datasetId, patch as any)
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
            This feature uses the Claude AI API to analyse your paper. An{' '}
            <strong>ANTHROPIC_API_KEY</strong> must be set in the backend environment.
            Your PDF is sent to the Anthropic API — do not upload unpublished or confidential work.
          </Alert>
          <DropZone onFile={handleFile} />
        </>
      )}

      {loading && (
        <Box textAlign="center" py={8}>
          <CircularProgress size={52} sx={{ mb: 2 }} />
          <Typography variant="h6" gutterBottom>Analysing paper…</Typography>
          <Typography variant="body2" color="text.secondary">
            Extracting text and running LLM extraction — this usually takes 10–30 seconds.
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
                    {Math.round(paperExtraction._chars_extracted / 1000)} k chars extracted ·{' '}
                    {paperExtraction._chars_sent < paperExtraction._chars_extracted ? 'truncated to 100 k · ' : ''}
                    extraction complete
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
