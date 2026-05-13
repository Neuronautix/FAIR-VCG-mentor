import SaveIcon from '@mui/icons-material/Save'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  FormControl,
  Grid,
  InputLabel,
  MenuItem,
  Select,
  Snackbar,
  TextField,
  Typography,
} from '@mui/material'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getMetadata, saveMetadata } from '../api/client'
import { useStore } from '../store/useStore'
import type { DatasetMetadata } from '../store/useStore'
import ArrowForwardIcon from '@mui/icons-material/ArrowForward'

const LICENSES = [
  'CC BY 4.0',
  'CC BY-SA 4.0',
  'CC BY-NC 4.0',
  'CC BY-NC-SA 4.0',
  'CC0 1.0',
  'Apache 2.0',
  'MIT',
  'Proprietary',
  'Other',
]

const ACCESS_OPTIONS = [
  'Open access',
  'Restricted — institutional use only',
  'Restricted — request required',
  'Embargoed until publication',
  'Internal only',
]

const STUDY_TYPES = [
  'In vivo — rodent',
  'In vivo — non-human primate',
  'In vivo — other species',
  'In vitro — cell culture',
  'In vitro — organoid',
  'Ex vivo',
  'Clinical — observational',
  'Clinical — interventional',
  'Survey',
  'Other',
]

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Box sx={{ mb: 3 }}>
      <Typography variant="subtitle2" fontWeight={700} color="primary" sx={{ mb: 1.5, textTransform: 'uppercase', letterSpacing: 0.5, fontSize: 12 }}>
        {title}
      </Typography>
      {children}
    </Box>
  )
}

function FieldLabel({ text, fromPaper }: { text: string; fromPaper: boolean }) {
  return (
    <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
      {text}
      {fromPaper && <Chip label="from paper" size="small" color="info" sx={{ fontSize: 10, height: 18 }} />}
    </span>
  )
}

export default function MetadataWizardPage() {
  const navigate = useNavigate()
  const { datasetId, metadata, setMetadata, setFairScore, columns, tableStructure, paperExtraction } = useStore()
  const [form, setForm] = useState<DatasetMetadata>(metadata)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [paperFilledFields, setPaperFilledFields] = useState<Set<string>>(new Set())
  const [paperAlertDismissed, setPaperAlertDismissed] = useState(false)

  useEffect(() => {
    if (datasetId) {
      getMetadata(datasetId)
        .then((r) => {
          const fetched = r.metadata
          setForm((prev) => {
            const merged = { ...prev, ...fetched }

            if (paperExtraction) {
              const dm = paperExtraction.dataset_metadata
              const filled = new Set<string>()

              const tryFill = (formKey: keyof DatasetMetadata, paperValue: string | string[] | null) => {
                if (paperValue != null) {
                  const current = merged[formKey]
                  const isEmpty = !current || (Array.isArray(current) ? current.length === 0 : current === '')
                  if (isEmpty) {
                    if (Array.isArray(paperValue)) {
                      ;(merged as any)[formKey] = paperValue
                    } else {
                      ;(merged as any)[formKey] = paperValue
                    }
                    filled.add(formKey)
                  }
                }
              }

              tryFill('title', dm.title)
              tryFill('description', dm.description)
              tryFill('creator', dm.creator)
              tryFill('institution', dm.institution)
              tryFill('species', dm.species)
              tryFill('license', dm.license)
              tryFill('funding_source', dm.funding_source)
              tryFill('protocol_reference', dm.protocol_reference)
              if (dm.keywords && dm.keywords.length > 0) {
                const current = merged.keywords
                const isEmpty = !current || current.length === 0
                if (isEmpty) {
                  merged.keywords = dm.keywords
                  filled.add('keywords')
                }
              }

              if (filled.size > 0) {
                setPaperFilledFields(filled)
              }

              return merged
            }

            return merged
          })
        })
        .catch(() => setError('Failed to load existing metadata.'))
    }
  }, [datasetId]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!datasetId) {
    return <Alert severity="info">No dataset loaded. Please upload a CSV first.</Alert>
  }

  const f = (field: keyof DatasetMetadata) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((prev) => ({ ...prev, [field]: e.target.value }))

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    try {
      const result = await saveMetadata(datasetId, form)
      setMetadata(result.metadata)
      setFairScore(null) // invalidate score so it recalculates
      setSaved(true)
    } catch {
      setError('Failed to save metadata.')
    } finally {
      setSaving(false)
    }
  }

  const identifiers = tableStructure?.detected_identifiers ?? []
  const identifierOptions = identifiers.length > 0 ? identifiers : columns.map((c) => c.name)

  const fp = (field: string) => paperFilledFields.has(field)

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Box>
          <Typography variant="h5">Metadata Wizard</Typography>
          <Typography variant="body2" color="text.secondary">
            Complete metadata improves your FAIR score and enables richer exports
          </Typography>
        </Box>
        <Button
          variant="contained"
          startIcon={saving ? <CircularProgress size={16} color="inherit" /> : <SaveIcon />}
          onClick={handleSave}
          disabled={saving}
        >
          Save metadata
        </Button>
      </Box>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {paperFilledFields.size > 0 && !paperAlertDismissed && paperExtraction && (
        <Alert severity="info" sx={{ mb: 2 }} onClose={() => setPaperAlertDismissed(true)}>
          {paperFilledFields.size} field(s) pre-filled from &ldquo;{paperExtraction._filename}&rdquo; — review before saving.
        </Alert>
      )}

      <Grid container spacing={3}>
        <Grid item xs={12} md={7}>
          <Card>
            <CardContent>
              <Section title="Dataset Identity">
                <Grid container spacing={2}>
                  <Grid item xs={12}>
                    <TextField
                      label={<FieldLabel text="Dataset title *" fromPaper={fp('title')} />}
                      fullWidth size="small" value={form.title ?? ''} onChange={f('title')}
                    />
                  </Grid>
                  <Grid item xs={12}>
                    <TextField
                      label={<FieldLabel text="Description" fromPaper={fp('description')} />}
                      fullWidth
                      size="small"
                      multiline
                      rows={3}
                      value={form.description ?? ''}
                      onChange={f('description')}
                      placeholder="Brief description of what this dataset contains and its purpose."
                    />
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <TextField
                      label={<FieldLabel text="Creator / Author *" fromPaper={fp('creator')} />}
                      fullWidth size="small" value={form.creator ?? ''} onChange={f('creator')}
                    />
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <TextField
                      label={<FieldLabel text="Institution" fromPaper={fp('institution')} />}
                      fullWidth size="small" value={form.institution ?? ''} onChange={f('institution')}
                    />
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <TextField label="Contact email" fullWidth size="small" type="email" value={form.contact_email ?? ''} onChange={f('contact_email')} />
                  </Grid>
                  <Grid item xs={12} sm={3}>
                    <TextField label="Date created" fullWidth size="small" type="date" InputLabelProps={{ shrink: true }} value={form.date_created ?? ''} onChange={f('date_created')} />
                  </Grid>
                  <Grid item xs={12} sm={3}>
                    <TextField label="Version" fullWidth size="small" value={form.version ?? ''} onChange={f('version')} placeholder="1.0" />
                  </Grid>
                </Grid>
              </Section>

              <Divider sx={{ my: 2 }} />

              <Section title="Access &amp; License">
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={6}>
                    <FormControl size="small" fullWidth>
                      <InputLabel>
                        <FieldLabel text="License *" fromPaper={fp('license')} />
                      </InputLabel>
                      <Select
                        label={<FieldLabel text="License *" fromPaper={fp('license')} />}
                        value={form.license ?? ''}
                        onChange={(e) => setForm((p) => ({ ...p, license: e.target.value }))}
                      >
                        {LICENSES.map((l) => <MenuItem key={l} value={l}>{l}</MenuItem>)}
                      </Select>
                    </FormControl>
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <FormControl size="small" fullWidth>
                      <InputLabel>Access conditions</InputLabel>
                      <Select label="Access conditions" value={form.access_conditions ?? ''} onChange={(e) => setForm((p) => ({ ...p, access_conditions: e.target.value }))}>
                        {ACCESS_OPTIONS.map((o) => <MenuItem key={o} value={o}>{o}</MenuItem>)}
                      </Select>
                    </FormControl>
                  </Grid>
                  <Grid item xs={12}>
                    <TextField
                      label={<FieldLabel text="Keywords (comma-separated)" fromPaper={fp('keywords')} />}
                      fullWidth
                      size="small"
                      value={form.keywords?.join(', ') ?? ''}
                      onChange={(e) => setForm((p) => ({ ...p, keywords: e.target.value.split(',').map((k) => k.trim()).filter(Boolean) }))}
                      placeholder="mouse, open field, anxiety, pharmacology"
                    />
                  </Grid>
                </Grid>
              </Section>

              <Divider sx={{ my: 2 }} />

              <Section title="Experimental Context">
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={6}>
                    <TextField
                      label={<FieldLabel text="Species" fromPaper={fp('species')} />}
                      fullWidth size="small" value={form.species ?? ''} onChange={f('species')} placeholder="Mus musculus"
                    />
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <FormControl size="small" fullWidth>
                      <InputLabel>Study type</InputLabel>
                      <Select label="Study type" value={form.study_type ?? ''} onChange={(e) => setForm((p) => ({ ...p, study_type: e.target.value }))}>
                        {STUDY_TYPES.map((t) => <MenuItem key={t} value={t}>{t}</MenuItem>)}
                      </Select>
                    </FormControl>
                  </Grid>
                  <Grid item xs={12}>
                    <TextField
                      label={<FieldLabel text="Protocol reference" fromPaper={fp('protocol_reference')} />}
                      fullWidth
                      size="small"
                      value={form.protocol_reference ?? ''}
                      onChange={f('protocol_reference')}
                      placeholder="Protocol ID, DOI, or URL"
                    />
                  </Grid>
                  <Grid item xs={12}>
                    <TextField
                      label={<FieldLabel text="Funding source" fromPaper={fp('funding_source')} />}
                      fullWidth size="small" value={form.funding_source ?? ''} onChange={f('funding_source')}
                    />
                  </Grid>
                </Grid>
              </Section>

              <Divider sx={{ my: 2 }} />

              <Section title="Table Semantics">
                <Grid container spacing={2}>
                  <Grid item xs={12}>
                    <TextField
                      label="What does one row represent?"
                      fullWidth
                      size="small"
                      value={form.row_represents ?? ''}
                      onChange={f('row_represents')}
                      placeholder="e.g. one animal-timepoint observation"
                    />
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <FormControl size="small" fullWidth>
                      <InputLabel>Primary identifier column</InputLabel>
                      <Select label="Primary identifier column" value={form.primary_identifier ?? ''} onChange={(e) => setForm((p) => ({ ...p, primary_identifier: e.target.value }))}>
                        {identifierOptions.map((c) => <MenuItem key={c} value={c}>{c}</MenuItem>)}
                      </Select>
                    </FormControl>
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <TextField
                      label="Base URI for your lab/project"
                      fullWidth
                      size="small"
                      value={form.base_uri ?? ''}
                      onChange={f('base_uri')}
                      placeholder="https://your-lab.org"
                    />
                  </Grid>
                </Grid>
              </Section>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={5}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Why metadata matters
              </Typography>
              <Typography variant="body2" color="text.secondary" paragraph>
                <strong>Findable:</strong> A title, description, and base URI allow the dataset to be
                discovered and referenced by others, even without a repository.
              </Typography>
              <Typography variant="body2" color="text.secondary" paragraph>
                <strong>Accessible:</strong> A license tells potential reusers what they are allowed
                to do with the data. Without a license, data is not legally reusable even if
                technically available.
              </Typography>
              <Typography variant="body2" color="text.secondary" paragraph>
                <strong>Interoperable:</strong> The base URI is used to generate machine-readable
                identifiers for your dataset, variables, and entities. Internal URIs are sufficient
                for an MVP — external ontology mappings can be added later.
              </Typography>
              <Typography variant="body2" color="text.secondary">
                <strong>Reusable:</strong> A protocol reference lets others reproduce your experiment.
                Creator and date information enable provenance tracking and citation.
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Box sx={{ display: 'flex', gap: 2, justifyContent: 'flex-end', mt: 3 }}>
        <Button variant="outlined" onClick={() => navigate('/fair-score')}>
          Back to FAIR Score
        </Button>
        <Button
          variant="contained"
          endIcon={<ArrowForwardIcon />}
          onClick={async () => { await handleSave(); navigate('/export') }}
          disabled={saving}
        >
          Save and Export
        </Button>
      </Box>

      <Snackbar open={saved} autoHideDuration={3000} onClose={() => setSaved(false)}>
        <Alert severity="success" onClose={() => setSaved(false)}>
          Metadata saved. Your FAIR score will update when you return to the FAIR Score page.
        </Alert>
      </Snackbar>
    </Box>
  )
}
