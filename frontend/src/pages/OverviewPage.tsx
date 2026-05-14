import ArrowForwardIcon from '@mui/icons-material/ArrowForward'
import RuleIcon from '@mui/icons-material/Rule'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  Grid,
  Link,
  Typography,
} from '@mui/material'
import { useNavigate } from 'react-router-dom'
import IssueCard from '../components/IssueCard'
import { useStore } from '../store/useStore'

const SHAPE_LABELS: Record<string, string> = {
  one_row_per_entity: 'One row per entity',
  repeated_measures_long_format: 'Repeated measures — long format',
  repeated_measures: 'Repeated measures',
  wide_measurement_format: 'Wide format with multiple measurement columns',
  tabular_data: 'Tabular data',
}

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

export default function OverviewPage() {
  const navigate = useNavigate()
  const { importInfo, tableStructure, columns, issues, templateId, templateCandidates, availableTemplates } =
    useStore()
  const activeTemplate = (() => {
    if (!templateId) return null
    const all = [...availableTemplates.builtin, ...availableTemplates.user]
    const found = all.find((t) => t.id === templateId)
    if (found) return found
    const cand = templateCandidates.find((c) => c.id === templateId)
    return cand ? { id: cand.id, name: cand.name } : { id: templateId, name: templateId }
  })()

  if (!importInfo || !tableStructure) {
    return (
      <Alert severity="info">
        No dataset loaded. Please <Button onClick={() => navigate('/')}>upload a CSV</Button> first.
      </Alert>
    )
  }

  const highIssues = issues.filter((i) => i.severity === 'high')
  const medIssues = issues.filter((i) => i.severity === 'medium')
  const lowIssues = issues.filter((i) => i.severity === 'low')

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 3 }}>
        <Box>
          <Typography variant="h5">Dataset Overview</Typography>
          <Typography variant="body2" color="text.secondary">
            {importInfo.filename}
          </Typography>
        </Box>
        <Button
          variant="contained"
          endIcon={<ArrowForwardIcon />}
          onClick={() => navigate('/columns')}
        >
          Inspect Columns
        </Button>
      </Box>

      <Box sx={{ mb: 2 }}>
        {activeTemplate ? (
          <Chip
            icon={<RuleIcon />}
            label={`Template: ${activeTemplate.name}`}
            size="small"
            color="primary"
            variant="outlined"
            onClick={() => navigate('/templates')}
            sx={{ cursor: 'pointer' }}
          />
        ) : (
          <Link
            component="button"
            onClick={() => navigate('/templates')}
            sx={{ fontSize: 13 }}
          >
            No template assigned — browse templates
          </Link>
        )}
      </Box>

      <Grid container spacing={2} sx={{ mb: 3 }}>
        {[
          { label: 'Rows', value: importInfo.n_rows.toLocaleString() },
          { label: 'Columns', value: importInfo.n_columns },
          { label: 'Encoding', value: importInfo.encoding },
          { label: 'Delimiter', value: importInfo.delimiter === ',' ? 'comma' : importInfo.delimiter },
          { label: 'Issues', value: issues.length, alert: highIssues.length > 0 },
        ].map((stat) => (
          <Grid item xs={6} sm={4} md={2.4} key={stat.label}>
            <Card>
              <CardContent sx={{ textAlign: 'center', py: 2 }}>
                <Typography
                  variant="h4"
                  fontWeight={800}
                  color={stat.alert ? 'error.main' : 'primary.main'}
                >
                  {stat.value}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {stat.label}
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      <Grid container spacing={3}>
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Table Structure
              </Typography>
              <Box sx={{ mb: 1 }}>
                <Typography variant="caption" color="text.secondary">
                  SHAPE
                </Typography>
                <Typography variant="body1" fontWeight={600}>
                  {SHAPE_LABELS[tableStructure.table_shape] ?? tableStructure.table_shape}
                </Typography>
              </Box>
              <Box sx={{ mb: 1 }}>
                <Typography variant="caption" color="text.secondary">
                  ONE ROW REPRESENTS
                </Typography>
                <Typography variant="body1" fontWeight={600}>
                  {tableStructure.row_represents.replace(/_/g, ' ')}
                </Typography>
              </Box>
              {(tableStructure.detected_identifiers ?? []).length > 0 && (
                <Box sx={{ mb: 1 }}>
                  <Typography variant="caption" color="text.secondary">
                    IDENTIFIERS
                  </Typography>
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mt: 0.5 }}>
                    {(tableStructure.detected_identifiers ?? []).map((id) => (
                      <Chip key={id} label={id} size="small" color="secondary" />
                    ))}
                  </Box>
                </Box>
              )}
              {(tableStructure.detected_measurements ?? []).length > 0 && (
                <Box sx={{ mb: 1 }}>
                  <Typography variant="caption" color="text.secondary">
                    MEASUREMENTS
                  </Typography>
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mt: 0.5 }}>
                    {(tableStructure.detected_measurements ?? []).map((m) => (
                      <Chip key={m} label={m} size="small" variant="outlined" color="warning" />
                    ))}
                  </Box>
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Column Types
              </Typography>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75 }}>
                {columns.map((col) => (
                  <Chip
                    key={col.name}
                    label={col.name}
                    size="small"
                    sx={{
                      background: (TYPE_COLORS[col.inferred_type] ?? '#9e9e9e') + '22',
                      color: TYPE_COLORS[col.inferred_type] ?? '#9e9e9e',
                      borderColor: TYPE_COLORS[col.inferred_type] ?? '#9e9e9e',
                      fontWeight: 500,
                    }}
                    variant="outlined"
                  />
                ))}
              </Box>

              <Divider sx={{ my: 2 }} />

              <Typography variant="caption" color="text.secondary">
                COLUMN TYPE LEGEND
              </Typography>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mt: 0.5 }}>
                {Object.entries(TYPE_COLORS).map(([type, color]) => (
                  <Chip
                    key={type}
                    label={type.replace(/_/g, ' ')}
                    size="small"
                    sx={{ background: color + '22', color, borderColor: color, fontSize: 10 }}
                    variant="outlined"
                  />
                ))}
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                <Typography variant="h6">
                  Data Quality Issues ({issues.length})
                </Typography>
                <Box sx={{ display: 'flex', gap: 1 }}>
                  {highIssues.length > 0 && <Chip label={`${highIssues.length} high`} size="small" color="error" />}
                  {medIssues.length > 0 && <Chip label={`${medIssues.length} medium`} size="small" color="warning" />}
                  {lowIssues.length > 0 && <Chip label={`${lowIssues.length} low`} size="small" color="info" />}
                </Box>
              </Box>
              {issues.length === 0 ? (
                <Alert severity="success">No major issues detected in this dataset.</Alert>
              ) : (
                [...highIssues, ...medIssues, ...lowIssues].map((issue) => (
                  <IssueCard key={issue.id} issue={issue} />
                ))
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  )
}
