import SaveIcon from '@mui/icons-material/Save'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  FormControl,
  Grid,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Snackbar,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { updateColumns } from '../api/client'
import { useStore } from '../store/useStore'
import type { ColumnProfile } from '../store/useStore'

const SEMANTIC_TYPES = [
  'identifier',
  'biological_descriptor',
  'experimental_condition',
  'measurement',
  'time_variable',
  'free_text_note',
  'metadata_field',
  'categorical',
  'unknown',
]

const DATA_TYPES = ['string', 'number', 'integer', 'categorical', 'date', 'boolean']

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

function ColumnEditor({
  col,
  onChange,
}: {
  col: ColumnProfile
  onChange: (updated: ColumnProfile) => void
}) {
  return (
    <Grid container spacing={1.5}>
      <Grid item xs={12} sm={6} md={3}>
        <TextField
          label="Label"
          size="small"
          fullWidth
          value={col.user_label ?? col.label ?? col.name}
          onChange={(e) => onChange({ ...col, user_label: e.target.value })}
        />
      </Grid>
      <Grid item xs={12} sm={6} md={3}>
        <TextField
          label="Description"
          size="small"
          fullWidth
          value={col.user_description ?? ''}
          onChange={(e) => onChange({ ...col, user_description: e.target.value })}
        />
      </Grid>
      <Grid item xs={6} sm={4} md={2}>
        <FormControl size="small" fullWidth>
          <InputLabel>Semantic type</InputLabel>
          <Select
            label="Semantic type"
            value={col.user_type ?? col.inferred_type}
            onChange={(e) => onChange({ ...col, user_type: e.target.value })}
          >
            {SEMANTIC_TYPES.map((t) => (
              <MenuItem key={t} value={t}>
                {t.replace(/_/g, ' ')}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </Grid>
      <Grid item xs={6} sm={4} md={2}>
        <FormControl size="small" fullWidth>
          <InputLabel>Data type</InputLabel>
          <Select
            label="Data type"
            value={col.user_type ? col.data_type : col.data_type}
            onChange={(e) => onChange({ ...col, data_type: e.target.value })}
          >
            {DATA_TYPES.map((t) => (
              <MenuItem key={t} value={t}>
                {t}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </Grid>
      <Grid item xs={6} sm={4} md={1}>
        <TextField
          label="Unit"
          size="small"
          fullWidth
          value={col.user_unit ?? ''}
          onChange={(e) => onChange({ ...col, user_unit: e.target.value })}
          placeholder={col.unit_guess ?? ''}
        />
      </Grid>
      <Grid item xs={6} sm={6} md={1}>
        <TextField
          label="Allowed values"
          size="small"
          fullWidth
          value={col.allowed_values?.join('|') ?? ''}
          onChange={(e) =>
            onChange({
              ...col,
              allowed_values: e.target.value ? e.target.value.split('|').map((v) => v.trim()) : null,
            })
          }
          placeholder="a|b|c"
        />
      </Grid>
    </Grid>
  )
}

export default function ColumnProfilePage() {
  const navigate = useNavigate()
  const { datasetId, columns, setColumns, setIssues } = useStore()
  const [localCols, setLocalCols] = useState<ColumnProfile[]>(columns)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [expanded, setExpanded] = useState<string | null>(null)

  if (!datasetId) {
    return <Alert severity="info">No dataset loaded. Please upload a CSV first.</Alert>
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const result = await updateColumns(datasetId, localCols)
      setColumns(result.columns)
      setIssues(result.issues)
      setLocalCols(result.columns)
      setSaved(true)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h5">Column Profile</Typography>
        <Button
          variant="contained"
          startIcon={saving ? <CircularProgress size={16} color="inherit" /> : <SaveIcon />}
          onClick={handleSave}
          disabled={saving}
        >
          Save changes
        </Button>
      </Box>

      <Alert severity="info" sx={{ mb: 2 }}>
        Review and correct the automatic column classification below. Descriptions and units are used
        to generate the data dictionary, CSVW, and JSON-LD exports.
      </Alert>

      {/* Summary table */}
      <Card sx={{ mb: 3 }}>
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow sx={{ background: '#f5f7fa' }}>
                <TableCell>Column</TableCell>
                <TableCell>Semantic type</TableCell>
                <TableCell>Data type</TableCell>
                <TableCell>Unit</TableCell>
                <TableCell align="right">Unique</TableCell>
                <TableCell align="right">Missing %</TableCell>
                <TableCell>Sample values</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {localCols.map((col) => (
                <TableRow
                  key={col.name}
                  hover
                  selected={expanded === col.name}
                  sx={{ cursor: 'pointer' }}
                  onClick={() => setExpanded(expanded === col.name ? null : col.name)}
                >
                  <TableCell>
                    <Typography variant="body2" fontWeight={600}>
                      {col.name}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Chip
                      label={(col.user_type ?? col.inferred_type).replace(/_/g, ' ')}
                      size="small"
                      sx={{
                        background: (TYPE_COLORS[col.user_type ?? col.inferred_type] ?? '#9e9e9e') + '22',
                        color: TYPE_COLORS[col.user_type ?? col.inferred_type] ?? '#9e9e9e',
                        fontSize: 11,
                      }}
                    />
                  </TableCell>
                  <TableCell>
                    <Typography variant="caption">{col.data_type}</Typography>
                  </TableCell>
                  <TableCell>
                    <Typography variant="caption" color={col.user_unit ? 'text.primary' : 'text.secondary'}>
                      {col.user_unit || col.unit_guess || '—'}
                    </Typography>
                  </TableCell>
                  <TableCell align="right">
                    <Typography variant="caption">{col.unique_values}</Typography>
                  </TableCell>
                  <TableCell align="right">
                    <Typography
                      variant="caption"
                      color={col.missing_pct > 20 ? 'error.main' : 'text.secondary'}
                    >
                      {col.missing_pct}%
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
                      {col.sample_values.slice(0, 3).join(', ')}
                    </Typography>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </Card>

      {/* Expanded editor */}
      {expanded && (
        <Paper variant="outlined" sx={{ p: 2, mb: 3, border: '2px solid #1976d2' }}>
          <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 1.5 }}>
            Editing: {expanded}
          </Typography>
          <ColumnEditor
            col={localCols.find((c) => c.name === expanded)!}
            onChange={(updated) =>
              setLocalCols((prev) => prev.map((c) => (c.name === updated.name ? updated : c)))
            }
          />
        </Paper>
      )}

      <Box sx={{ display: 'flex', gap: 2, justifyContent: 'flex-end' }}>
        <Button variant="outlined" onClick={() => navigate('/fair-score')}>
          Skip to FAIR Score
        </Button>
        <Button
          variant="contained"
          onClick={async () => { await handleSave(); navigate('/fair-score') }}
          disabled={saving}
        >
          Save and continue
        </Button>
      </Box>

      <Snackbar open={saved} autoHideDuration={3000} onClose={() => setSaved(false)}>
        <Alert severity="success" onClose={() => setSaved(false)}>
          Column mappings saved.
        </Alert>
      </Snackbar>
    </Box>
  )
}
