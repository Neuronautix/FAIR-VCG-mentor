import RefreshIcon from '@mui/icons-material/Refresh'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Grid,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Typography,
} from '@mui/material'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getFairScore } from '../api/client'
import FAIRScoreBreakdown from '../components/FAIRScoreBreakdown'
import { useStore } from '../store/useStore'
import ArrowForwardIcon from '@mui/icons-material/ArrowForward'
import LightbulbOutlinedIcon from '@mui/icons-material/LightbulbOutlined'

export default function FAIRScorePage() {
  const navigate = useNavigate()
  const { datasetId, fairScore, setFairScore } = useStore()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

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
