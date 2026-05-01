import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  FormControl,
  Grid,
  InputLabel,
  MenuItem,
  Select,
  Slider,
  Step,
  StepLabel,
  Stepper,
  TextField,
  Typography,
} from '@mui/material'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getVCGWizardPrefill, saveVCGWizard, startVCGGeneration } from '../api/client'
import { useStore } from '../store/useStore'

const STEPS = ['Research Context', 'Column Roles', 'Statistical Config', 'Review & Generate']

interface FormState {
  // Step 1
  domain: string
  study_type: string
  design: string
  // Step 2
  treatment_col: string
  control_value: string
  outcome_cols: string[]
  covariate_cols: string[]
  // Step 3
  method: string
  n_synthetic: number
  confidence_level: number
  seed: number
}

const defaultForm: FormState = {
  domain: '',
  study_type: 'parallel_group',
  design: 'parallel_group',
  treatment_col: '',
  control_value: '',
  outcome_cols: [],
  covariate_cols: [],
  method: 'auto',
  n_synthetic: 30,
  confidence_level: 0.95,
  seed: 42,
}

export default function VCGWizardPage() {
  const navigate = useNavigate()
  const { datasetId, columns, setVCGStatus } = useStore()

  const [activeStep, setActiveStep] = useState(0)
  const [form, setForm] = useState<FormState>(defaultForm)
  const [saving, setSaving] = useState(false)

  // Prefill on step 2 mount
  useEffect(() => {
    if (activeStep === 1 && datasetId) {
      getVCGWizardPrefill(datasetId)
        .then((data: Partial<FormState>) => {
          setForm((prev) => ({ ...prev, ...data }))
        })
        .catch(() => {
          // prefill unavailable — ignore
        })
    }
  }, [activeStep, datasetId])

  const allColumnNames = columns.map((c) => c.name)
  const numericColumns = columns.filter((c) =>
    ['integer', 'float', 'numeric', 'number'].includes((c.data_type ?? '').toLowerCase())
  )
  const bioColumns = columns.filter((c) =>
    (c.inferred_type ?? '').toLowerCase().includes('biological') ||
    (c.inferred_type ?? '').toLowerCase().includes('descriptor')
  )

  const toggleItem = (list: string[], item: string): string[] =>
    list.includes(item) ? list.filter((x) => x !== item) : [...list, item]

  const saveCurrentStep = async () => {
    if (!datasetId) return
    setSaving(true)
    try {
      await saveVCGWizard(datasetId, form)
    } catch {
      // non-fatal — continue
    } finally {
      setSaving(false)
    }
  }

  const handleNext = async () => {
    await saveCurrentStep()
    setActiveStep((s) => s + 1)
  }

  const handleBack = () => setActiveStep((s) => s - 1)

  const handleGenerate = async () => {
    if (!datasetId) return
    setSaving(true)
    try {
      await saveVCGWizard(datasetId, form)
      await startVCGGeneration(datasetId)
      setVCGStatus('running')
      navigate('/vcg')
    } catch {
      // show nothing — vcg page handles error states
    } finally {
      setSaving(false)
    }
  }

  if (!datasetId) {
    return (
      <Box sx={{ mt: 2 }}>
        <Typography color="error">No dataset loaded. Please upload a CSV first.</Typography>
      </Box>
    )
  }

  return (
    <Box>
      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3 }}>
        <Box>
          <Typography variant="h5">VCG Configuration Wizard</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            Configure your virtual control group using the step-by-step form.
          </Typography>
        </Box>
        <Button variant="outlined" onClick={() => navigate('/vcg')}>
          Open Chat
        </Button>
      </Box>

      <Stepper activeStep={activeStep} sx={{ mb: 4 }}>
        {STEPS.map((label) => (
          <Step key={label}>
            <StepLabel>{label}</StepLabel>
          </Step>
        ))}
      </Stepper>

      {/* Step 1 — Research Context */}
      {activeStep === 0 && (
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Research Context
            </Typography>
            <Grid container spacing={3}>
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  label="Research domain"
                  placeholder="e.g. pharmacology, neuroscience"
                  value={form.domain}
                  onChange={(e) => setForm({ ...form, domain: e.target.value })}
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <FormControl fullWidth>
                  <InputLabel>Study type</InputLabel>
                  <Select
                    value={form.study_type}
                    label="Study type"
                    onChange={(e) => setForm({ ...form, study_type: e.target.value })}
                  >
                    <MenuItem value="dose_response">Dose–response</MenuItem>
                    <MenuItem value="parallel_group">Parallel group</MenuItem>
                    <MenuItem value="longitudinal">Longitudinal</MenuItem>
                    <MenuItem value="observational">Observational</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              <Grid item xs={12} sm={6}>
                <FormControl fullWidth>
                  <InputLabel>Experimental design</InputLabel>
                  <Select
                    value={form.design}
                    label="Experimental design"
                    onChange={(e) => setForm({ ...form, design: e.target.value })}
                  >
                    <MenuItem value="parallel_group">Parallel group</MenuItem>
                    <MenuItem value="crossover">Crossover</MenuItem>
                    <MenuItem value="repeated_measures">Repeated measures</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
            </Grid>
          </CardContent>
        </Card>
      )}

      {/* Step 2 — Column Roles */}
      {activeStep === 1 && (
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Column Roles
            </Typography>
            <Grid container spacing={3}>
              <Grid item xs={12} sm={6}>
                <FormControl fullWidth>
                  <InputLabel>Treatment column</InputLabel>
                  <Select
                    value={form.treatment_col}
                    label="Treatment column"
                    onChange={(e) => setForm({ ...form, treatment_col: e.target.value })}
                  >
                    {allColumnNames.map((col) => (
                      <MenuItem key={col} value={col}>
                        {col}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  label="Control group label"
                  placeholder='e.g. "Vehicle" or "Placebo"'
                  value={form.control_value}
                  onChange={(e) => setForm({ ...form, control_value: e.target.value })}
                />
              </Grid>

              {/* Outcome columns */}
              <Grid item xs={12}>
                <Typography variant="subtitle2" gutterBottom>
                  Outcome columns (select all that apply)
                </Typography>
                {numericColumns.length === 0 ? (
                  <Typography variant="body2" color="text.secondary">
                    No numeric columns detected.
                  </Typography>
                ) : (
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                    {numericColumns.map((col) => {
                      const selected = form.outcome_cols.includes(col.name)
                      return (
                        <Chip
                          key={col.name}
                          label={col.name}
                          clickable
                          color={selected ? 'primary' : 'default'}
                          variant={selected ? 'filled' : 'outlined'}
                          onClick={() =>
                            setForm({ ...form, outcome_cols: toggleItem(form.outcome_cols, col.name) })
                          }
                        />
                      )
                    })}
                  </Box>
                )}
              </Grid>

              {/* Covariate columns */}
              <Grid item xs={12}>
                <Typography variant="subtitle2" gutterBottom>
                  Covariate columns (select all that apply)
                </Typography>
                {bioColumns.length === 0 ? (
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                    {allColumnNames.map((col) => {
                      const selected = form.covariate_cols.includes(col)
                      return (
                        <Chip
                          key={col}
                          label={col}
                          clickable
                          color={selected ? 'secondary' : 'default'}
                          variant={selected ? 'filled' : 'outlined'}
                          onClick={() =>
                            setForm({
                              ...form,
                              covariate_cols: toggleItem(form.covariate_cols, col),
                            })
                          }
                        />
                      )
                    })}
                  </Box>
                ) : (
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                    {bioColumns.map((col) => {
                      const selected = form.covariate_cols.includes(col.name)
                      return (
                        <Chip
                          key={col.name}
                          label={col.name}
                          clickable
                          color={selected ? 'secondary' : 'default'}
                          variant={selected ? 'filled' : 'outlined'}
                          onClick={() =>
                            setForm({
                              ...form,
                              covariate_cols: toggleItem(form.covariate_cols, col.name),
                            })
                          }
                        />
                      )
                    })}
                  </Box>
                )}
              </Grid>

              {/* Preview of selected outcome columns */}
              {form.outcome_cols.length > 0 && (
                <Grid item xs={12}>
                  <Typography variant="subtitle2" gutterBottom>
                    Selected outcome preview
                  </Typography>
                  <Box
                    component="table"
                    sx={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}
                  >
                    <thead>
                      <tr>
                        <td style={{ fontWeight: 600, padding: '4px 8px', borderBottom: '1px solid #eee' }}>Column</td>
                        <td style={{ fontWeight: 600, padding: '4px 8px', borderBottom: '1px solid #eee' }}>Type</td>
                        <td style={{ fontWeight: 600, padding: '4px 8px', borderBottom: '1px solid #eee' }}>Missing %</td>
                      </tr>
                    </thead>
                    <tbody>
                      {form.outcome_cols.map((colName) => {
                        const colData = columns.find((c) => c.name === colName)
                        return (
                          <tr key={colName}>
                            <td style={{ padding: '4px 8px' }}>{colName}</td>
                            <td style={{ padding: '4px 8px' }}>{colData?.data_type ?? '—'}</td>
                            <td style={{ padding: '4px 8px' }}>
                              {colData ? `${colData.missing_pct.toFixed(1)}%` : '—'}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </Box>
                </Grid>
              )}
            </Grid>
          </CardContent>
        </Card>
      )}

      {/* Step 3 — Statistical Config */}
      {activeStep === 2 && (
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Statistical Configuration
            </Typography>
            <Grid container spacing={3}>
              <Grid item xs={12} sm={6}>
                <FormControl fullWidth>
                  <InputLabel>Generation method</InputLabel>
                  <Select
                    value={form.method}
                    label="Generation method"
                    onChange={(e) => setForm({ ...form, method: e.target.value })}
                  >
                    <MenuItem value="auto">Auto (recommended)</MenuItem>
                    <MenuItem value="bootstrap">Bootstrap — resample from real control subjects</MenuItem>
                    <MenuItem value="synthetic">Synthetic — generate from fitted distribution</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  type="number"
                  label="Number of synthetic subjects"
                  value={form.n_synthetic}
                  inputProps={{ min: 10, max: 500 }}
                  onChange={(e) =>
                    setForm({ ...form, n_synthetic: Math.min(500, Math.max(10, Number(e.target.value))) })
                  }
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  type="number"
                  label="Random seed"
                  value={form.seed}
                  onChange={(e) => setForm({ ...form, seed: Number(e.target.value) })}
                />
              </Grid>
              <Grid item xs={12}>
                <Typography variant="subtitle2" gutterBottom>
                  Confidence level: {(form.confidence_level * 100).toFixed(0)}%
                </Typography>
                <Slider
                  value={form.confidence_level}
                  min={0.8}
                  max={0.99}
                  step={0.01}
                  onChange={(_e, val) => setForm({ ...form, confidence_level: val as number })}
                  valueLabelDisplay="auto"
                  valueLabelFormat={(v) => `${(v * 100).toFixed(0)}%`}
                />
              </Grid>
            </Grid>
          </CardContent>
        </Card>
      )}

      {/* Step 4 — Review & Generate */}
      {activeStep === 3 && (
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Review &amp; Generate
            </Typography>
            <Grid container spacing={2}>
              {[
                { label: 'Domain', value: form.domain || '—' },
                { label: 'Study type', value: form.study_type },
                { label: 'Design', value: form.design },
                { label: 'Treatment column', value: form.treatment_col || '—' },
                { label: 'Control label', value: form.control_value || '—' },
                { label: 'Outcome columns', value: form.outcome_cols.join(', ') || '—' },
                { label: 'Covariate columns', value: form.covariate_cols.join(', ') || '—' },
                { label: 'Method', value: form.method },
                { label: 'N synthetic', value: String(form.n_synthetic) },
                { label: 'Confidence level', value: `${(form.confidence_level * 100).toFixed(0)}%` },
                { label: 'Seed', value: String(form.seed) },
              ].map(({ label, value }) => (
                <Grid item xs={12} sm={6} key={label}>
                  <Typography variant="caption" color="text.secondary">
                    {label}
                  </Typography>
                  <Typography variant="body2">{value}</Typography>
                </Grid>
              ))}
            </Grid>
            <Box sx={{ mt: 3 }}>
              <Button
                variant="contained"
                size="large"
                onClick={handleGenerate}
                disabled={saving}
              >
                {saving ? 'Starting…' : 'Generate VCG'}
              </Button>
            </Box>
          </CardContent>
        </Card>
      )}

      {/* Navigation */}
      <Box sx={{ display: 'flex', gap: 2, mt: 3 }}>
        {activeStep > 0 && activeStep < 3 && (
          <Button variant="outlined" onClick={handleBack}>
            Back
          </Button>
        )}
        {activeStep < 3 && (
          <Button variant="contained" onClick={handleNext} disabled={saving}>
            {saving ? 'Saving…' : 'Next'}
          </Button>
        )}
        {activeStep === 3 && (
          <Button variant="outlined" onClick={handleBack}>
            Back
          </Button>
        )}
      </Box>
    </Box>
  )
}
