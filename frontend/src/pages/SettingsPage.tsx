import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import DeleteIcon from '@mui/icons-material/Delete'
import KeyIcon from '@mui/icons-material/Key'
import WifiIcon from '@mui/icons-material/Wifi'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Divider,
  Grid,
  InputAdornment,
  TextField,
  Typography,
} from '@mui/material'
import { useEffect, useState } from 'react'
import {
  clearAnthropicKey,
  clearOpenAIKey,
  getAnthropicKeyStatus,
  getOpenAIKeyStatus,
  storeAnthropicKey,
  storeOpenAIKey,
  testAnthropicKey,
  testOpenAIKey,
} from '../api/client'
import { useStore } from '../store/useStore'

async function refreshAIStatus(setAIConfigured: (v: boolean) => void) {
  try {
    const r = await fetch('/api/llm/status')
    const data = await r.json()
    setAIConfigured(data.enabled ?? false)
  } catch {
    // non-fatal
  }
}

export default function SettingsPage() {
  const { aiConfigured, setAIConfigured } = useStore()

  // OpenAI state
  const [openaiKey, setOpenaiKey] = useState('')
  const [openaiModel, setOpenaiModel] = useState<string | null>(null)
  const [openaiConfigured, setOpenaiConfigured] = useState(false)
  const [openaiSaving, setOpenaiSaving] = useState(false)
  const [openaiClearing, setOpenaiClearing] = useState(false)
  const [openaiTesting, setOpenaiTesting] = useState(false)
  const [openaiTestResult, setOpenaiTestResult] = useState<{ ok: boolean; message: string } | null>(null)
  const [openaiSaveError, setOpenaiSaveError] = useState<string | null>(null)
  const [openaiSaved, setOpenaiSaved] = useState(false)

  // Anthropic state
  const [anthropicKey, setAnthropicKey] = useState('')
  const [anthropicModel, setAnthropicModel] = useState<string | null>(null)
  const [anthropicConfigured, setAnthropicConfigured] = useState(false)
  const [anthropicSaving, setAnthropicSaving] = useState(false)
  const [anthropicClearing, setAnthropicClearing] = useState(false)
  const [anthropicTesting, setAnthropicTesting] = useState(false)
  const [anthropicTestResult, setAnthropicTestResult] = useState<{ ok: boolean; message: string } | null>(null)
  const [anthropicSaveError, setAnthropicSaveError] = useState<string | null>(null)
  const [anthropicSaved, setAnthropicSaved] = useState(false)

  useEffect(() => {
    getOpenAIKeyStatus()
      .then((data) => { setOpenaiConfigured(data.configured); if (data.model) setOpenaiModel(data.model) })
      .catch(() => {})
    getAnthropicKeyStatus()
      .then((data) => { setAnthropicConfigured(data.configured); if (data.model) setAnthropicModel(data.model) })
      .catch(() => {})
  }, [])

  // ── OpenAI handlers ──────────────────────────────────────────────────────

  const handleOpenAISave = async () => {
    if (!openaiKey.trim()) return
    setOpenaiSaving(true); setOpenaiSaveError(null); setOpenaiSaved(false); setOpenaiTestResult(null)
    try {
      await storeOpenAIKey(openaiKey.trim())
      const status = await getOpenAIKeyStatus()
      setOpenaiConfigured(status.configured)
      if (status.model) setOpenaiModel(status.model)
      setOpenaiKey('')
      setOpenaiSaved(true)
      await refreshAIStatus(setAIConfigured)
    } catch (err: any) {
      setOpenaiSaveError(err?.response?.data?.detail || 'Failed to save key.')
    } finally {
      setOpenaiSaving(false)
    }
  }

  const handleOpenAIClear = async () => {
    setOpenaiClearing(true); setOpenaiTestResult(null); setOpenaiSaved(false)
    try {
      await clearOpenAIKey()
      setOpenaiConfigured(false); setOpenaiModel(null)
      await refreshAIStatus(setAIConfigured)
    } finally {
      setOpenaiClearing(false)
    }
  }

  const handleOpenAITest = async () => {
    setOpenaiTesting(true); setOpenaiTestResult(null)
    try {
      const result = await testOpenAIKey()
      setOpenaiTestResult({
        ok: result.ok,
        message: result.ok ? `Connection successful. Response: "${result.response}"` : `Connection failed: ${result.error}`,
      })
    } catch (err: any) {
      setOpenaiTestResult({ ok: false, message: err?.response?.data?.detail || 'Connection test failed.' })
    } finally {
      setOpenaiTesting(false)
    }
  }

  // ── Anthropic handlers ───────────────────────────────────────────────────

  const handleAnthropicSave = async () => {
    if (!anthropicKey.trim()) return
    setAnthropicSaving(true); setAnthropicSaveError(null); setAnthropicSaved(false); setAnthropicTestResult(null)
    try {
      await storeAnthropicKey(anthropicKey.trim())
      const status = await getAnthropicKeyStatus()
      setAnthropicConfigured(status.configured)
      if (status.model) setAnthropicModel(status.model)
      setAnthropicKey('')
      setAnthropicSaved(true)
      await refreshAIStatus(setAIConfigured)
    } catch (err: any) {
      setAnthropicSaveError(err?.response?.data?.detail || 'Failed to save key.')
    } finally {
      setAnthropicSaving(false)
    }
  }

  const handleAnthropicClear = async () => {
    setAnthropicClearing(true); setAnthropicTestResult(null); setAnthropicSaved(false)
    try {
      await clearAnthropicKey()
      setAnthropicConfigured(false); setAnthropicModel(null)
      await refreshAIStatus(setAIConfigured)
    } finally {
      setAnthropicClearing(false)
    }
  }

  const handleAnthropicTest = async () => {
    setAnthropicTesting(true); setAnthropicTestResult(null)
    try {
      const result = await testAnthropicKey()
      setAnthropicTestResult({
        ok: result.ok,
        message: result.ok ? `Connection successful. Response: "${result.response}"` : `Connection failed: ${result.error}`,
      })
    } catch (err: any) {
      setAnthropicTestResult({ ok: false, message: err?.response?.data?.detail || 'Connection test failed.' })
    } finally {
      setAnthropicTesting(false)
    }
  }

  return (
    <Box>
      <Typography variant="h5" gutterBottom>
        Settings
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Configure optional features. No account required to use FAIR assessment.
      </Typography>

      <Alert severity="info" sx={{ mb: 3 }}>
        <Typography variant="body2" gutterBottom>
          <strong>API keys are stored only in server memory.</strong>
        </Typography>
        <Typography variant="body2">
          Keys are never written to disk, never saved to the database, and never returned in any
          API response. They will be lost if the server restarts.
        </Typography>
      </Alert>

      {!aiConfigured && (
        <Alert severity="warning" sx={{ mb: 3 }}>
          No AI provider configured. AI suggestion features are disabled. Add an Anthropic or
          OpenAI key below.
        </Alert>
      )}

      {aiConfigured && (
        <Alert severity="success" icon={<CheckCircleIcon />} sx={{ mb: 3 }}>
          AI suggestions are active.
        </Alert>
      )}

      <Grid container spacing={3}>
        {/* Anthropic card */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 2 }}>
                <KeyIcon color="secondary" />
                <Box>
                  <Typography variant="h6">Anthropic API Key</Typography>
                  <Typography variant="caption" color="text.secondary">
                    Powers Claude Haiku — HITL suggestions, template fill, vocabulary discovery
                  </Typography>
                </Box>
              </Box>

              {anthropicConfigured && (
                <Alert severity="success" icon={<CheckCircleIcon />} sx={{ mb: 2 }}>
                  Configured.{anthropicModel ? ` Model: ${anthropicModel}` : ''}
                </Alert>
              )}

              <TextField
                label="Anthropic API Key"
                type="password"
                fullWidth
                size="small"
                value={anthropicKey}
                onChange={(e) => { setAnthropicKey(e.target.value); setAnthropicSaved(false); setAnthropicSaveError(null) }}
                placeholder="sk-ant-..."
                InputProps={{ startAdornment: <InputAdornment position="start"><KeyIcon fontSize="small" /></InputAdornment> }}
                sx={{ mb: 2 }}
                helperText="Your key is never shown after submission."
              />

              {anthropicSaveError && (
                <Alert severity="error" sx={{ mb: 2 }} onClose={() => setAnthropicSaveError(null)}>{anthropicSaveError}</Alert>
              )}
              {anthropicSaved && (
                <Alert severity="success" sx={{ mb: 2 }} icon={<CheckCircleIcon />}>Key saved successfully.</Alert>
              )}
              {anthropicTestResult && (
                <Alert severity={anthropicTestResult.ok ? 'success' : 'error'} sx={{ mb: 2 }}>{anthropicTestResult.message}</Alert>
              )}

              <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                <Button
                  variant="contained"
                  color="secondary"
                  onClick={handleAnthropicSave}
                  disabled={anthropicSaving || !anthropicKey.trim()}
                  startIcon={anthropicSaving ? <CircularProgress size={16} color="inherit" /> : <KeyIcon />}
                >
                  {anthropicSaving ? 'Saving…' : 'Save Key'}
                </Button>
                {anthropicConfigured && (
                  <>
                    <Button
                      variant="outlined"
                      onClick={handleAnthropicTest}
                      disabled={anthropicTesting}
                      startIcon={anthropicTesting ? <CircularProgress size={16} /> : <WifiIcon />}
                    >
                      {anthropicTesting ? 'Testing…' : 'Test'}
                    </Button>
                    <Button
                      variant="outlined"
                      color="error"
                      onClick={handleAnthropicClear}
                      disabled={anthropicClearing}
                      startIcon={anthropicClearing ? <CircularProgress size={16} /> : <DeleteIcon />}
                    >
                      {anthropicClearing ? 'Clearing…' : 'Clear'}
                    </Button>
                  </>
                )}
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* OpenAI card */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 2 }}>
                <KeyIcon color="primary" />
                <Box>
                  <Typography variant="h6">OpenAI API Key</Typography>
                  <Typography variant="caption" color="text.secondary">
                    Fallback provider — metadata suggestions, improvement checklist
                  </Typography>
                </Box>
              </Box>

              {openaiConfigured && (
                <Alert severity="success" icon={<CheckCircleIcon />} sx={{ mb: 2 }}>
                  Configured.{openaiModel ? ` Model: ${openaiModel}` : ''}
                </Alert>
              )}

              <TextField
                label="OpenAI API Key"
                type="password"
                fullWidth
                size="small"
                value={openaiKey}
                onChange={(e) => { setOpenaiKey(e.target.value); setOpenaiSaved(false); setOpenaiSaveError(null) }}
                placeholder="sk-..."
                InputProps={{ startAdornment: <InputAdornment position="start"><KeyIcon fontSize="small" /></InputAdornment> }}
                sx={{ mb: 2 }}
                helperText="Your key is never shown after submission."
              />

              {openaiSaveError && (
                <Alert severity="error" sx={{ mb: 2 }} onClose={() => setOpenaiSaveError(null)}>{openaiSaveError}</Alert>
              )}
              {openaiSaved && (
                <Alert severity="success" sx={{ mb: 2 }} icon={<CheckCircleIcon />}>Key saved successfully.</Alert>
              )}
              {openaiTestResult && (
                <Alert severity={openaiTestResult.ok ? 'success' : 'error'} sx={{ mb: 2 }}>{openaiTestResult.message}</Alert>
              )}

              <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                <Button
                  variant="contained"
                  onClick={handleOpenAISave}
                  disabled={openaiSaving || !openaiKey.trim()}
                  startIcon={openaiSaving ? <CircularProgress size={16} color="inherit" /> : <KeyIcon />}
                >
                  {openaiSaving ? 'Saving…' : 'Save Key'}
                </Button>
                {openaiConfigured && (
                  <>
                    <Button
                      variant="outlined"
                      onClick={handleOpenAITest}
                      disabled={openaiTesting}
                      startIcon={openaiTesting ? <CircularProgress size={16} /> : <WifiIcon />}
                    >
                      {openaiTesting ? 'Testing…' : 'Test'}
                    </Button>
                    <Button
                      variant="outlined"
                      color="error"
                      onClick={handleOpenAIClear}
                      disabled={openaiClearing}
                      startIcon={openaiClearing ? <CircularProgress size={16} /> : <DeleteIcon />}
                    >
                      {openaiClearing ? 'Clearing…' : 'Clear'}
                    </Button>
                  </>
                )}
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="h6" gutterBottom>
                What AI suggestions can do &amp; privacy guarantee
              </Typography>
              <Divider sx={{ mb: 2 }} />
              <Grid container spacing={3}>
                <Grid item xs={12} md={6}>
                  <Box component="ul" sx={{ pl: 2.5, '& li': { mb: 1 }, mt: 0 }}>
                    <li><Typography variant="body2"><strong>Metadata suggestions</strong> — improve dataset title and description based on detected issues.</Typography></li>
                    <li><Typography variant="body2"><strong>Column descriptions</strong> — concise descriptions from name, type, and sample values.</Typography></li>
                    <li><Typography variant="body2"><strong>Improvement checklist</strong> — prioritised FAIR, ARRIVE, and PREPARE action list.</Typography></li>
                    <li><Typography variant="body2"><strong>Template fill</strong> — suggest values for required reporting fields (Anthropic only).</Typography></li>
                    <li><Typography variant="body2"><strong>Vocabulary discovery</strong> — propose ontology terms and schema extensions (Anthropic only).</Typography></li>
                  </Box>
                </Grid>
                <Grid item xs={12} md={6}>
                  <Typography variant="subtitle2" color="primary" gutterBottom>Privacy</Typography>
                  <Box component="ul" sx={{ pl: 2.5, '& li': { mb: 0.5 }, mt: 0 }}>
                    <li><Typography variant="body2">Raw dataset rows are <strong>never sent</strong> to any AI provider.</Typography></li>
                    <li><Typography variant="body2">Only metadata, column names, and issue summaries are sent.</Typography></li>
                    <li><Typography variant="body2">A preview of what will be sent is shown before each AI call.</Typography></li>
                    <li><Typography variant="body2">Keys are stored only in server RAM — cleared on restart.</Typography></li>
                  </Box>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  )
}
