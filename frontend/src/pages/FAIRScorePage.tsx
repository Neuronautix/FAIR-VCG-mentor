import RefreshIcon from '@mui/icons-material/Refresh'
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Grid,
  IconButton,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Tooltip,
  Typography,
} from '@mui/material'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  getFairScore,
  getLLMFairScore,
  listHITLSuggestions,
  requestLLMIssueFixes,
} from '../api/client'
import FAIRScoreBreakdown from '../components/FAIRScoreBreakdown'
import HITLPanel from '../components/HITLPanel'
import { useStore } from '../store/useStore'
import ArrowForwardIcon from '@mui/icons-material/ArrowForward'
import LightbulbOutlinedIcon from '@mui/icons-material/LightbulbOutlined'

const VERDICT_COLOR: Record<string, 'success' | 'warning' | 'error' | 'default'> = {
  good: 'success',
  adequate: 'warning',
  weak: 'error',
}

const DIMENSION_LABELS: Record<string, string> = {
  findable: 'Findable',
  accessible: 'Accessible',
  interoperable: 'Interoperable',
  reusable: 'Reusable',
}

export default function FAIRScorePage() {
  const navigate = useNavigate()
  const {
    datasetId,
    fairScore,
    setFairScore,
    llmFairScore,
    setLLMFairScore,
    setHITLSuggestions,
  } = useStore()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [llmLoading, setLlmLoading] = useState(false)
  const [llmError, setLlmError] = useState<string | null>(null)
  const [issueFixLoading, setIssueFixLoading] = useState(false)

  const requestIssueFixes = async () => {
    if (!datasetId) return
    setIssueFixLoading(true)
    try {
      await requestLLMIssueFixes(datasetId)
      const fresh = await listHITLSuggestions(datasetId)
      setHITLSuggestions(fresh)
    } finally {
      setIssueFixLoading(false)
    }
  }

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

  const fetchLLMScore = async () => {
    if (!datasetId) return
    setLlmLoading(true)
    setLlmError(null)
    try {
      const result = await getLLMFairScore(datasetId)
      setLLMFairScore(result)
    } catch (e: any) {
      const msg: string = e?.response?.data?.detail ?? e?.message ?? 'Unknown error'
      if (msg.includes('API_KEY') || msg.includes('provider')) {
        setLlmError('AI assessment requires a configured local or cloud LLM provider.')
      } else {
        setLlmError('AI assessment failed. Please try again.')
      }
    } finally {
      setLlmLoading(false)
    }
  }

  useEffect(() => {
    if (datasetId && !fairScore) load()
  }, [datasetId, fairScore]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!datasetId) {
    return <Alert severity="info">No dataset loaded. Please upload a CSV first.</Alert>
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
        emptyHint="Click 'Ask LLM' to propose concrete fixes for the detected FAIR issues."
        refreshAction={{
          label: 'Ask LLM',
          onClick: requestIssueFixes,
          pending: issueFixLoading,
        }}
        onApplied={() => {
          // metadata may have changed; let the FAIR score recompute on next mount
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
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
                  <Typography variant="h6">AI Assessment</Typography>
                  {llmFairScore && (
                    <Tooltip title="Refresh AI assessment">
                      <IconButton
                        size="small"
                        onClick={() => { setLLMFairScore(null); fetchLLMScore() }}
                        disabled={llmLoading}
                      >
                        <RefreshIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  )}
                </Box>

                {!llmFairScore && !llmLoading && !llmError && (
                  <Box>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                      The configured LLM analyses whether your metadata is substantively complete.
                    </Typography>
                    <Button
                      variant="outlined"
                      startIcon={<AutoAwesomeIcon />}
                      onClick={fetchLLMScore}
                    >
                      Get AI Assessment
                    </Button>
                  </Box>
                )}

                {llmLoading && (
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                    <CircularProgress size={20} />
                    <Typography variant="body2" color="text.secondary">
                      The configured LLM is analysing your metadata…
                    </Typography>
                  </Box>
                )}

                {llmError && (
                  <Alert severity="error" sx={{ mt: 1 }}>
                    {llmError}
                  </Alert>
                )}

                {llmFairScore && !llmLoading && (
                  <Box>
                    {llmFairScore.overall_assessment && (
                      <Typography variant="body2" sx={{ mb: 2 }}>
                        {llmFairScore.overall_assessment}
                      </Typography>
                    )}

                    {llmFairScore.top_priority && (
                      <Alert severity="warning" sx={{ mb: 2 }}>
                        <strong>Top priority:</strong> {llmFairScore.top_priority}
                      </Alert>
                    )}

                    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                      {Object.entries(DIMENSION_LABELS).map(([key, label]) => {
                        const dim = llmFairScore[key]
                        if (!dim) return null
                        const verdict: string = (dim.verdict ?? '').toLowerCase()
                        const color = VERDICT_COLOR[verdict] ?? 'default'
                        return (
                          <Box key={key} sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
                            <Box sx={{ minWidth: 100, pt: 0.25 }}>
                              <Typography variant="caption" fontWeight={700} sx={{ mr: 0.5 }}>
                                {label}
                              </Typography>
                              <Chip
                                label={dim.verdict ?? '—'}
                                size="small"
                                color={color}
                                sx={{ height: 18, fontSize: 10 }}
                              />
                            </Box>
                            <Typography variant="body2" color="text.secondary">
                              {dim.commentary ?? dim.comment ?? ''}
                            </Typography>
                          </Box>
                        )
                      })}
                    </Box>
                  </Box>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  What FAIR means for your data
                </Typography>
                <Typography variant="body2" color="text.secondary" paragraph>
                  <strong>A CSV file is not "bad" because it is CSV.</strong> CSV becomes weak when it
                  is isolated from metadata. Adding a data dictionary, stable identifiers, units,
                  controlled vocabularies, provenance, a license, and a JSON-LD or RO-Crate package
                  transforms a raw CSV into a much more reusable and machine-actionable research
                  object.
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Complete the Metadata Wizard to improve your score, then export all artifacts
                  from the Export page.
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}

      <Box sx={{ display: 'flex', gap: 2, justifyContent: 'flex-end', mt: 3 }}>
        <Button variant="outlined" onClick={() => navigate('/columns')}>
          Back to Columns
        </Button>
        <Button
          variant="contained"
          endIcon={<ArrowForwardIcon />}
          onClick={() => navigate('/metadata')}
        >
          Add Metadata
        </Button>
      </Box>
    </Box>
  )
}
