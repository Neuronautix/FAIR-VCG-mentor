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
  clearOpenAIKey,
  getOpenAIKeyStatus,
  storeOpenAIKey,
  testOpenAIKey,
} from '../api/client'
import { useStore } from '../store/useStore'

export default function SettingsPage() {
  const { aiConfigured, setAIConfigured } = useStore()
  const [apiKey, setApiKey] = useState('')
  const [model, setModel] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [clearing, setClearing] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    getOpenAIKeyStatus()
      .then((data) => {
        setAIConfigured(data.configured)
        if (data.model) setModel(data.model)
      })
      .catch(() => setAIConfigured(false))
  }, [setAIConfigured])

  const handleSave = async () => {
    if (!apiKey.trim()) return
    setSaving(true)
    setSaveError(null)
    setSaved(false)
    setTestResult(null)
    try {
      await storeOpenAIKey(apiKey.trim())
      const status = await getOpenAIKeyStatus()
      setAIConfigured(status.configured)
      if (status.model) setModel(status.model)
      setApiKey('')
      setSaved(true)
    } catch (err: any) {
      setSaveError(err?.response?.data?.detail || 'Failed to save key. Please try again.')
    } finally {
      setSaving(false)
    }
  }

  const handleClear = async () => {
    setClearing(true)
    setTestResult(null)
    setSaved(false)
    try {
      await clearOpenAIKey()
      setAIConfigured(false)
      setModel(null)
    } finally {
      setClearing(false)
    }
  }

  const handleTest = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      const result = await testOpenAIKey()
      setTestResult({
        ok: result.ok,
        message: result.ok
          ? `Connection successful. Response: "${result.response}"`
          : `Connection failed: ${result.error}`,
      })
    } catch (err: any) {
      setTestResult({ ok: false, message: err?.response?.data?.detail || 'Connection test failed.' })
    } finally {
      setTesting(false)
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

      <Grid container spacing={3}>
        <Grid item xs={12} md={7}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 2 }}>
                <KeyIcon color="primary" />
                <Typography variant="h6">OpenAI API Key (Optional)</Typography>
              </Box>

              <Alert severity="info" sx={{ mb: 3 }}>
                <Typography variant="body2" gutterBottom>
                  <strong>Your API key is stored only in server memory.</strong>
                </Typography>
                <Typography variant="body2">
                  It is never written to disk, never saved to the database, and never returned in any
                  API response. It will be lost if the server restarts. You can clear it at any time.
                </Typography>
              </Alert>

              {aiConfigured && (
                <Alert severity="success" icon={<CheckCircleIcon />} sx={{ mb: 2 }}>
                  An OpenAI API key is currently configured.{model ? ` Model: ${model}` : ''}
                </Alert>
              )}

              {!aiConfigured && (
                <Alert severity="warning" sx={{ mb: 2 }}>
                  No OpenAI API key configured. AI suggestion features are disabled.
                </Alert>
              )}

              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Enter your OpenAI API key to enable AI-powered suggestions for dataset metadata,
                column descriptions, and improvement checklists. The key is used only to make
                OpenAI API calls — never for any other purpose.
              </Typography>

              <TextField
                label="OpenAI API Key"
                type="password"
                fullWidth
                size="small"
                value={apiKey}
                onChange={(e) => {
                  setApiKey(e.target.value)
                  setSaved(false)
                  setSaveError(null)
                }}
                placeholder="sk-..."
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <KeyIcon fontSize="small" />
                    </InputAdornment>
                  ),
                }}
                sx={{ mb: 2 }}
                helperText="Your key is never shown after submission."
              />

              {saveError && (
                <Alert severity="error" sx={{ mb: 2 }} onClose={() => setSaveError(null)}>
                  {saveError}
                </Alert>
              )}

              {saved && (
                <Alert severity="success" sx={{ mb: 2 }} icon={<CheckCircleIcon />}>
                  Key saved successfully.
                </Alert>
              )}

              {testResult && (
                <Alert severity={testResult.ok ? 'success' : 'error'} sx={{ mb: 2 }}>
                  {testResult.message}
                </Alert>
              )}

              <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap' }}>
                <Button
                  variant="contained"
                  onClick={handleSave}
                  disabled={saving || !apiKey.trim()}
                  startIcon={saving ? <CircularProgress size={16} color="inherit" /> : <KeyIcon />}
                >
                  {saving ? 'Saving…' : 'Save Key'}
                </Button>

                {aiConfigured && (
                  <>
                    <Button
                      variant="outlined"
                      color="primary"
                      onClick={handleTest}
                      disabled={testing}
                      startIcon={testing ? <CircularProgress size={16} /> : <WifiIcon />}
                    >
                      {testing ? 'Testing…' : 'Test Connection'}
                    </Button>

                    <Button
                      variant="outlined"
                      color="error"
                      onClick={handleClear}
                      disabled={clearing}
                      startIcon={clearing ? <CircularProgress size={16} /> : <DeleteIcon />}
                    >
                      {clearing ? 'Clearing…' : 'Clear Key'}
                    </Button>
                  </>
                )}
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={5}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                What AI suggestions can do
              </Typography>
              <Divider sx={{ mb: 2 }} />

              <Box component="ul" sx={{ pl: 2.5, '& li': { mb: 1 } }}>
                <li>
                  <Typography variant="body2">
                    <strong>Metadata suggestions</strong> — suggest improvements to your dataset
                    title and description based on detected issues.
                  </Typography>
                </li>
                <li>
                  <Typography variant="body2">
                    <strong>Column descriptions</strong> — suggest concise descriptions for each
                    column based on name, type, and sample values.
                  </Typography>
                </li>
                <li>
                  <Typography variant="body2">
                    <strong>Improvement checklist</strong> — generate a prioritised checklist of
                    FAIR, ARRIVE, and PREPARE improvement actions.
                  </Typography>
                </li>
              </Box>

              <Divider sx={{ my: 2 }} />

              <Typography variant="subtitle2" gutterBottom color="primary">
                Privacy guarantee
              </Typography>
              <Box component="ul" sx={{ pl: 2.5, '& li': { mb: 0.5 } }}>
                <li>
                  <Typography variant="body2">
                    Raw dataset rows are <strong>never sent</strong> to OpenAI.
                  </Typography>
                </li>
                <li>
                  <Typography variant="body2">
                    Only metadata, column names, and issue summaries are sent.
                  </Typography>
                </li>
                <li>
                  <Typography variant="body2">
                    A preview of exactly what will be sent is shown before each AI call.
                  </Typography>
                </li>
                <li>
                  <Typography variant="body2">
                    Your API key is stored only in server RAM — cleared on restart.
                  </Typography>
                </li>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  )
}
