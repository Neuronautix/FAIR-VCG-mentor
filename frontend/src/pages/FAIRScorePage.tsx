import RefreshIcon from '@mui/icons-material/Refresh'
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome'
import ArrowForwardIcon from '@mui/icons-material/ArrowForward'
import LightbulbOutlinedIcon from '@mui/icons-material/LightbulbOutlined'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Grid,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Stack,
  Chip,
  Typography,
} from '@mui/material'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  getFairScore,
  getAIChecklist,
  previewAIChecklist,
} from '../api/client'
import FAIRScoreBreakdown from '../components/FAIRScoreBreakdown'
import HITLPanel from '../components/HITLPanel'
import { useStore } from '../store/useStore'

export default function FAIRScorePage() {
  const navigate = useNavigate()
  const {
    datasetId,
    fairScore,
    llmFairAnalysis,
    setFairScore,
    setHITLSuggestions,
    aiConfigured,
  } = useStore()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // AI checklist state
  const [checklistLoading, setChecklistLoading] = useState(false)
  const [checklistError, setChecklistError] = useState<string | null>(null)
  const [checklist, setChecklist] = useState<string | null>(null)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewData, setPreviewData] = useState<any>(null)
  const [previewLoading, setPreviewLoading] = useState(false)

  const load = async () => {
    if (!datasetId) return
    setLoading(true)
    setError(null)
    try {
      const score = await getFairScore(datasetId)
      setFairScore(score)
    } catch {
      setError('Could not compute FAIR score. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (datasetId && !fairScore) load()
  }, [datasetId, fairScore]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleAIChecklist = async () => {
    if (!datasetId) return
    setPreviewLoading(true)
    setChecklistError(null)
    try {
      const preview = await previewAIChecklist(datasetId)
      setPreviewData(preview.preview)
      setPreviewOpen(true)
    } catch (err: any) {
      setChecklistError(err?.response?.data?.detail || 'Preview failed.')
    } finally {
      setPreviewLoading(false)
    }
  }

  const handleConfirmChecklist = async () => {
    if (!datasetId) return
    setPreviewOpen(false)
    setChecklistLoading(true)
    setChecklistError(null)
    try {
      const result = await getAIChecklist(datasetId)
      setChecklist(result.checklist)
    } catch (err: any) {
      setChecklistError(err?.response?.data?.detail || 'AI checklist request failed.')
    } finally {
      setChecklistLoading(false)
    }
  }

  if (!datasetId) {
    return <Alert severity="info">No assessment loaded. Import research documents or start a session first.</Alert>
  }

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Box>
          <Typography variant="h5">FAIR-Readiness Score</Typography>
          <Typography variant="body2" color="text.secondary">
            Rule-based, transparent assessment — not a regulatory certification
          </Typography>
        </Box>
        <Button startIcon={<RefreshIcon />} variant="outlined" onClick={load} disabled={loading}>
          Recalculate
        </Button>
      </Box>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      <HITLPanel
        title="AI-suggested fixes — Human review required"
        emptyHint="No AI-suggested fixes yet. Use the 'Get Improvement Checklist' button below to generate suggestions."
        onApplied={() => {
          setFairScore(null)
          load()
        }}
      />

      {loading && (
        <Box sx={{ textAlign: 'center', py: 6 }}>
          <CircularProgress />
          <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
            Computing FAIR score…
          </Typography>
        </Box>
      )}

      {fairScore && !loading && (
        <Grid container spacing={3}>
          <Grid item xs={12} md={5}>
            <Card>
              <CardContent>
                <FAIRScoreBreakdown score={fairScore} />
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={7}>
            {llmFairAnalysis && (
              <Card sx={{ mb: 2, border: '1.5px solid #7c4dff' }}>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    LLM FAIR Analysis
                  </Typography>
                  <Typography variant="body2" color="text.secondary" paragraph>
                    {llmFairAnalysis.overall_assessment}
                  </Typography>
                  <Alert severity="info" sx={{ mb: 2 }}>
                    Top priority: {llmFairAnalysis.top_priority}
                  </Alert>
                  <Stack spacing={1}>
                    {(['findable', 'accessible', 'interoperable', 'reusable'] as const).map((dim) => (
                      <Box key={dim} sx={{ display: 'flex', gap: 1, alignItems: 'flex-start' }}>
                        <Chip
                          label={`${dim}: ${llmFairAnalysis[dim].verdict}`}
                          size="small"
                          color={
                            llmFairAnalysis[dim].verdict === 'good'
                              ? 'success'
                              : llmFairAnalysis[dim].verdict === 'adequate'
                                ? 'warning'
                                : 'error'
                          }
                          sx={{ textTransform: 'capitalize', minWidth: 130 }}
                        />
                        <Typography variant="body2" color="text.secondary">
                          {llmFairAnalysis[dim].commentary}
                        </Typography>
                      </Box>
                    ))}
                  </Stack>
                </CardContent>
              </Card>
            )}

            <Card sx={{ mb: 2 }}>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Recommended Next Actions
                </Typography>
                {fairScore.main_recommendations.length === 0 ? (
                  <Alert severity="success">Excellent! No major recommendations at this time.</Alert>
                ) : (
                  <List dense>
                    {fairScore.main_recommendations.map((rec, i) => (
                      <ListItem key={i} alignItems="flex-start" sx={{ py: 0.75 }}>
                        <ListItemIcon sx={{ minWidth: 32, mt: 0.5 }}>
                          <LightbulbOutlinedIcon fontSize="small" color="warning" />
                        </ListItemIcon>
                        <ListItemText
                          primary={rec}
                          primaryTypographyProps={{ fontSize: 14 }}
                        />
                      </ListItem>
                    ))}
                  </List>
                )}
              </CardContent>
            </Card>

            <Card sx={{ mb: 2 }}>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  AI Improvement Checklist
                </Typography>
                {!aiConfigured && (
                  <Alert severity="info" sx={{ mb: 2 }}>
                    Configure an OpenAI API key in{' '}
                    <Button size="small" onClick={() => navigate('/settings')} sx={{ p: 0, minWidth: 0, textDecoration: 'underline' }}>
                      Settings
                    </Button>{' '}
                    to get a prioritised AI improvement checklist.
                  </Alert>
                )}
                {aiConfigured && !checklist && !checklistLoading && (
                  <Box>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                      Get a prioritised checklist of FAIR, ARRIVE, and PREPARE improvement actions
                      generated by OpenAI based on your score breakdown.
                    </Typography>
                    {checklistError && (
                      <Alert severity="error" sx={{ mb: 2 }}>{checklistError}</Alert>
                    )}
                    <Button
                      variant="outlined"
                      startIcon={previewLoading ? <CircularProgress size={16} /> : <AutoAwesomeIcon />}
                      onClick={handleAIChecklist}
                      disabled={previewLoading}
                    >
                      Get Improvement Checklist
                    </Button>
                  </Box>
                )}
                {checklistLoading && (
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                    <CircularProgress size={20} />
                    <Typography variant="body2" color="text.secondary">
                      Generating checklist…
                    </Typography>
                  </Box>
                )}
                {checklist && !checklistLoading && (
                  <Box>
                    <Box
                      sx={{
                        fontFamily: 'monospace',
                        fontSize: 13,
                        whiteSpace: 'pre-wrap',
                        background: '#f5f5f5',
                        borderRadius: 1,
                        p: 2,
                        maxHeight: 400,
                        overflowY: 'auto',
                      }}
                    >
                      {checklist}
                    </Box>
                    <Button
                      size="small"
                      sx={{ mt: 1 }}
                      onClick={() => { setChecklist(null); setChecklistError(null) }}
                    >
                      Refresh
                    </Button>
                  </Box>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  What FAIR means for your data
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Complete the Metadata Wizard to improve your score, then export your assessment
                  reports from the Export page.
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}

      <Box sx={{ display: 'flex', gap: 2, justifyContent: 'flex-end', mt: 3 }}>
        <Button variant="outlined" onClick={() => navigate('/templates')}>
          Back to Templates
        </Button>
        <Button
          variant="contained"
          endIcon={<ArrowForwardIcon />}
          onClick={() => navigate('/metadata')}
        >
          Add Metadata
        </Button>
      </Box>

      {/* Preview dialog */}
      <Dialog open={previewOpen} onClose={() => setPreviewOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Preview — what will be sent to OpenAI</DialogTitle>
        <DialogContent>
          <Alert severity="info" sx={{ mb: 2 }}>
            {previewData?.note}
          </Alert>
          {previewData?.sent_fields && (
            <Box
              component="pre"
              sx={{ fontSize: 12, background: '#f5f5f5', p: 1.5, borderRadius: 1, overflowX: 'auto' }}
            >
              {JSON.stringify(previewData.sent_fields, null, 2)}
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPreviewOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleConfirmChecklist}>
            Confirm — Get Checklist
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
