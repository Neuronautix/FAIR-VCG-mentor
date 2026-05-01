import {
  Box,
  Card,
  CardContent,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material'

interface CovariateRow {
  col: string
  smd: number
  balance_label: string
}

interface OutcomeRow {
  col: string
  mean_real: number
  sd_real: number
  mean_vcg: number
  sd_vcg: number
  p_value: number
}

interface Props {
  covariates: CovariateRow[]
  outcomes: OutcomeRow[]
}

function smdChip(smd: number) {
  if (smd < 0.1) return <Chip label="Excellent" color="success" size="small" />
  if (smd <= 0.25) return <Chip label="Acceptable" color="warning" size="small" />
  return <Chip label="Poor" color="error" size="small" />
}

function pChip(p: number) {
  if (p > 0.05) return <Chip label="Similar distributions" color="success" size="small" />
  return <Chip label="Significant difference" color="warning" size="small" />
}

function sig(n: number): string {
  if (!isFinite(n)) return String(n)
  return Number(n.toPrecision(3)).toString()
}

export default function CovariateBalanceTable({ covariates, outcomes }: Props) {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      {/* Covariate Balance */}
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Covariate Balance
          </Typography>
          {covariates.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              No covariate data available.
            </Typography>
          ) : (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell><strong>Column</strong></TableCell>
                  <TableCell><strong>SMD</strong></TableCell>
                  <TableCell><strong>Assessment</strong></TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {covariates.map((row, i) => (
                  <TableRow key={i}>
                    <TableCell>{row.col}</TableCell>
                    <TableCell>{sig(row.smd)}</TableCell>
                    <TableCell>{smdChip(row.smd)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Outcome Comparison */}
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Outcome Comparison
          </Typography>
          {outcomes.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              No outcome data available.
            </Typography>
          ) : (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell><strong>Endpoint</strong></TableCell>
                  <TableCell><strong>Mean ± SD (Real)</strong></TableCell>
                  <TableCell><strong>Mean ± SD (VCG)</strong></TableCell>
                  <TableCell><strong>p-value</strong></TableCell>
                  <TableCell><strong>Assessment</strong></TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {outcomes.map((row, i) => (
                  <TableRow key={i}>
                    <TableCell>{row.col}</TableCell>
                    <TableCell>{sig(row.mean_real)} ± {sig(row.sd_real)}</TableCell>
                    <TableCell>{sig(row.mean_vcg)} ± {sig(row.sd_vcg)}</TableCell>
                    <TableCell>{sig(row.p_value)}</TableCell>
                    <TableCell>{pChip(row.p_value)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </Box>
  )
}
