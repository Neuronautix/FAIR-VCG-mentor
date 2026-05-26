import AddIcon from '@mui/icons-material/Add'
import ArticleIcon from '@mui/icons-material/Article'
import FactCheckIcon from '@mui/icons-material/FactCheck'
import SchemaIcon from '@mui/icons-material/Schema'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { useEffect, useMemo, useState } from 'react'
import {
  addStudyCorpusPaper,
  getStudyCorpus,
  listHITLSuggestions,
  ProjectSchema,
  requestCorpusSchemaReview,
  StudyCorpus,
  StudyCorpusSourceType,
  updateConsensusSchema,
  validateProjectSchema,
} from '../api/client'
import HITLPanel from '../components/HITLPanel'
import { useStore } from '../store/useStore'

const SOURCE_TYPES: StudyCorpusSourceType[] = ['doi', 'pdf', 'text']

type SchemaValidationResult = {
  ok: boolean
  errors: string[]
  warnings: string[]
  schema: ProjectSchema | null
}

export default function StudyCorpusPage() {
  const { datasetId, setHITLSuggestions } = useStore()
  const [corpus, setCorpus] = useState<StudyCorpus | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [reviewing, setReviewing] = useState(false)
  const [validatingSchema, setValidatingSchema] = useState(false)
  const [savingSchema, setSavingSchema] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [schemaMessage, setSchemaMessage] = useState<string | null>(null)
  const [sourceType, setSourceType] = useState<StudyCorpusSourceType>('doi')
  const [sourceRef, setSourceRef] = useState('')
  const [title, setTitle] = useState('')
  const [text, setText] = useState('')
  const [schemaDraft, setSchemaDraft] = useState('')
  const [schemaValidation, setSchemaValidation] = useState<SchemaValidationResult | null>(null)

  const load = async () => {
    if (!datasetId) return
    setLoading(true)
    setError(null)
    try {
      const data = await getStudyCorpus(datasetId)
      setCorpus(data)
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? err.message ?? 'Could not load study corpus.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetId])

  useEffect(() => {
    const consensus = corpus?.consensus_schema
    const schema =
      consensus?.schema ??
      corpus?.article_schema_candidates?.[corpus.article_schema_candidates.length - 1]?.schema ??
      { fields: [] }
    setSchemaDraft(JSON.stringify(schema, null, 2))
    setSchemaValidation(
      consensus?.validation ? { ...consensus.validation, schema: consensus.schema } : null,
    )
  }, [datasetId, corpus?.consensus_schema?.updated_at, corpus?.article_schema_candidates.length])

  const paperCount = corpus?.papers.length ?? 0
  const candidateCount = corpus?.article_schema_candidates.length ?? 0
  const openConflicts = useMemo(
    () => (corpus?.conflicts ?? []).filter((c) => c.status !== 'resolved'),
    [corpus],
  )

  const addPaper = async () => {
    if (!datasetId || !sourceRef.trim()) return
    setSaving(true)
    setError(null)
    try {
      const res = await addStudyCorpusPaper(datasetId, {
        source_type: sourceType,
        source_ref: sourceRef.trim(),
        title: title.trim() || null,
        text: sourceType === 'text' ? text.trim() : null,
      })
      setCorpus(res.corpus)
      setSourceRef('')
      setTitle('')
      setText('')
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? err.message ?? 'Could not add paper.')
    } finally {
      setSaving(false)
    }
  }

  const requestReview = async () => {
    if (!datasetId) return
    setReviewing(true)
    setError(null)
    try {
      await requestCorpusSchemaReview(datasetId)
      const fresh = await listHITLSuggestions(datasetId)
      setHITLSuggestions(fresh)
      await load()
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? err.message ?? 'Could not request schema review.')
    } finally {
      setReviewing(false)
    }
  }

  const parseSchemaDraft = (): Record<string, any> | null => {
    try {
      const parsed = JSON.parse(schemaDraft)
      if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
        setSchemaValidation({
          ok: false,
          errors: ['Schema draft must be a JSON object.'],
          warnings: [],
          schema: null,
        })
        return null
      }
      return parsed
    } catch (err: any) {
      setSchemaValidation({
        ok: false,
        errors: [`Invalid JSON: ${err.message}`],
        warnings: [],
        schema: null,
      })
      return null
    }
  }

  const validateSchemaDraft = async (): Promise<SchemaValidationResult | null> => {
    if (!datasetId) return null
    setError(null)
    setSchemaMessage(null)
    const parsed = parseSchemaDraft()
    if (!parsed) return null
    setValidatingSchema(true)
    try {
      const result = await validateProjectSchema(datasetId, parsed)
      setSchemaValidation(result)
      if (result.schema) {
        setSchemaDraft(JSON.stringify(result.schema, null, 2))
      }
      return result
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? err.message ?? 'Could not validate schema.')
      return null
    } finally {
      setValidatingSchema(false)
    }
  }

  const saveConsensusSchema = async () => {
    if (!datasetId) return
    setSavingSchema(true)
    setError(null)
    setSchemaMessage(null)
    try {
      const validation = schemaValidation?.ok ? schemaValidation : await validateSchemaDraft()
      if (!validation?.ok || !validation.schema) {
        setSchemaMessage('Resolve schema validation errors before saving.')
        return
      }
      const approvedSchema: ProjectSchema = { ...validation.schema, status: 'approved' }
      const res = await updateConsensusSchema(datasetId, {
        consensus_schema: approvedSchema,
        reason: 'Saved from study corpus schema approval workflow.',
      })
      const consensus = res.corpus.consensus_schema
      setCorpus(res.corpus)
      setSchemaValidation(
        consensus?.validation ? { ...consensus.validation, schema: consensus.schema } : validation,
      )
      setSchemaMessage('Consensus schema saved.')
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? err.message ?? 'Could not save consensus schema.')
    } finally {
      setSavingSchema(false)
    }
  }

  const normalizedSchema = schemaValidation?.schema
  const schemaColumnCount = normalizedSchema?.columns.length ?? 0
  const schemaMetadataCount = Object.keys(normalizedSchema?.metadata_fields ?? {}).length
  const schemaUnitCount = Object.keys(normalizedSchema?.units ?? {}).length

  if (!datasetId) {
    return (
      <Alert severity="info">
        Upload a dataset before building a study corpus for schema synthesis.
      </Alert>
    )
  }

  return (
    <Box>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ mb: 2 }}>
        <Card variant="outlined" sx={{ flex: 1 }}>
          <CardContent>
            <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
              <ArticleIcon color="primary" />
              <Typography variant="h6">Study Corpus</Typography>
            </Stack>
            <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
              <Chip label={`${paperCount} papers`} size="small" />
              <Chip label={`${candidateCount} article schemas`} size="small" />
              <Chip
                label={`${openConflicts.length} open conflicts`}
                size="small"
                color={openConflicts.length ? 'warning' : 'default'}
              />
            </Stack>
          </CardContent>
        </Card>

        <Card variant="outlined" sx={{ flex: 1 }}>
          <CardContent>
            <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
              <SchemaIcon color="primary" />
              <Typography variant="h6">Consensus Schema</Typography>
            </Stack>
            <Typography variant="body2" color="text.secondary">
              {Object.keys(corpus?.consensus_schema?.schema ?? {}).length
                ? `${Object.keys(corpus?.consensus_schema?.schema ?? {}).length} top-level fields`
                : 'No approved consensus fields yet'}
            </Typography>
          </CardContent>
        </Card>
      </Stack>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      <Card variant="outlined" sx={{ mb: 2 }}>
        <CardContent>
          <Stack
            direction={{ xs: 'column', md: 'row' }}
            spacing={1}
            alignItems={{ xs: 'stretch', md: 'center' }}
            sx={{ mb: 1.5 }}
          >
            <Stack direction="row" spacing={1} alignItems="center" sx={{ flexGrow: 1 }}>
              <SchemaIcon color="primary" />
              <Typography variant="subtitle1" fontWeight={700}>
                Consensus Schema Approval
              </Typography>
            </Stack>
            <Stack direction="row" spacing={1}>
              <Button
                variant="outlined"
                startIcon={validatingSchema ? <CircularProgress size={16} /> : <FactCheckIcon />}
                disabled={validatingSchema || savingSchema || !schemaDraft.trim()}
                onClick={validateSchemaDraft}
              >
                Validate Schema
              </Button>
              <Button
                variant="contained"
                startIcon={savingSchema ? <CircularProgress size={16} /> : <SchemaIcon />}
                disabled={validatingSchema || savingSchema || !schemaDraft.trim()}
                onClick={saveConsensusSchema}
              >
                Save Consensus Schema
              </Button>
            </Stack>
          </Stack>
          <TextField
            multiline
            minRows={8}
            maxRows={18}
            fullWidth
            label="Consensus schema draft JSON"
            value={schemaDraft}
            onChange={(e) => {
              setSchemaDraft(e.target.value)
              setSchemaValidation(null)
              setSchemaMessage(null)
            }}
            size="small"
            spellCheck={false}
            sx={{
              '& textarea': {
                fontFamily: 'monospace',
                fontSize: 13,
              },
            }}
          />
          <Stack spacing={1} sx={{ mt: 1.5 }}>
            {schemaValidation && (
              <Alert severity={schemaValidation.ok ? 'success' : 'error'}>
                {schemaValidation.ok ? 'Schema is valid.' : 'Schema has validation errors.'}
              </Alert>
            )}
            {!!schemaValidation?.errors.length && (
              <Alert severity="error">
                <Typography variant="body2" fontWeight={700}>
                  Errors
                </Typography>
                {schemaValidation.errors.map((item) => (
                  <Typography key={item} variant="body2">
                    {item}
                  </Typography>
                ))}
              </Alert>
            )}
            {!!schemaValidation?.warnings.length && (
              <Alert severity="warning">
                <Typography variant="body2" fontWeight={700}>
                  Warnings
                </Typography>
                {schemaValidation.warnings.map((item) => (
                  <Typography key={item} variant="body2">
                    {item}
                  </Typography>
                ))}
              </Alert>
            )}
            {normalizedSchema && (
              <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
                <Chip label={`${schemaColumnCount} normalized columns`} size="small" />
                <Chip label={`${schemaMetadataCount} metadata fields`} size="small" />
                <Chip label={`${schemaUnitCount} unit definitions`} size="small" />
                <Chip
                  label={normalizedSchema.vcg_readiness.ready ? 'VCG ready' : 'VCG not ready'}
                  size="small"
                  color={normalizedSchema.vcg_readiness.ready ? 'success' : 'default'}
                />
              </Stack>
            )}
            {schemaMessage && (
              <Alert severity={schemaMessage.includes('saved') ? 'success' : 'info'}>
                {schemaMessage}
              </Alert>
            )}
          </Stack>
        </CardContent>
      </Card>

      <Card variant="outlined" sx={{ mb: 2 }}>
        <CardContent>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 2 }}>
            <AddIcon color="primary" />
            <Typography variant="subtitle1" fontWeight={700}>
              Add Paper Source
            </Typography>
          </Stack>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5}>
            <TextField
              select
              size="small"
              label="Source"
              value={sourceType}
              onChange={(e) => setSourceType(e.target.value as StudyCorpusSourceType)}
              sx={{ minWidth: 120 }}
            >
              {SOURCE_TYPES.map((type) => (
                <MenuItem key={type} value={type}>
                  {type.toUpperCase()}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              size="small"
              label={sourceType === 'doi' ? 'DOI' : sourceType === 'pdf' ? 'PDF reference' : 'Text reference'}
              value={sourceRef}
              onChange={(e) => setSourceRef(e.target.value)}
              sx={{ flex: 1 }}
            />
            <TextField
              size="small"
              label="Title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              sx={{ flex: 1 }}
            />
            <Button
              variant="contained"
              startIcon={saving ? <CircularProgress size={16} /> : <AddIcon />}
              disabled={saving || !sourceRef.trim()}
              onClick={addPaper}
            >
              Add
            </Button>
          </Stack>
          {sourceType === 'text' && (
            <TextField
              multiline
              minRows={4}
              fullWidth
              label="Methods or dataset description"
              value={text}
              onChange={(e) => setText(e.target.value)}
              sx={{ mt: 1.5 }}
            />
          )}
        </CardContent>
      </Card>

      <Card variant="outlined" sx={{ mb: 2 }}>
        <CardContent>
          <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
            <FactCheckIcon color="primary" />
            <Typography variant="subtitle1" fontWeight={700} sx={{ flexGrow: 1 }}>
              Paper Sources
            </Typography>
            <Button
              variant="outlined"
              startIcon={reviewing ? <CircularProgress size={16} /> : <FactCheckIcon />}
              disabled={reviewing || loading || paperCount === 0}
              onClick={requestReview}
            >
              Schema Review
            </Button>
          </Stack>
          {loading && <CircularProgress size={20} />}
          {!loading && paperCount === 0 && (
            <Typography variant="body2" color="text.secondary">
              No paper sources have been added.
            </Typography>
          )}
          <Stack spacing={1}>
            {(corpus?.papers ?? []).map((paper) => (
              <Box key={paper.id}>
                <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} alignItems={{ md: 'center' }}>
                  <Chip label={paper.source_type.toUpperCase()} size="small" variant="outlined" />
                  <Typography variant="body2" fontWeight={600} sx={{ flex: 1 }}>
                    {paper.title || paper.source_ref}
                  </Typography>
                  <Chip label={paper.status} size="small" />
                </Stack>
                <Typography variant="caption" color="text.secondary">
                  {paper.source_ref}
                </Typography>
                <Divider sx={{ mt: 1 }} />
              </Box>
            ))}
          </Stack>
        </CardContent>
      </Card>

      <HITLPanel
        title="Scientific schema review"
        emptyHint="No schema review questions are pending."
        refreshAction={{ label: 'Schema Review', onClick: requestReview, pending: reviewing }}
        onApplied={load}
      />
    </Box>
  )
}
