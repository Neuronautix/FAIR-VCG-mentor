import axios from 'axios'
import type {
  ColumnProfile,
  DatasetMetadata,
  FAIRScore,
  ImportInfo,
  InferenceMetrics,
  Issue,
  LowConfidenceColumn,
  TableStructure,
} from '../store/useStore'

const api = axios.create({ baseURL: '/api' })

export interface UploadResponse {
  dataset_id: string
  import_info: ImportInfo
  columns: ColumnProfile[]
  table_structure: TableStructure
  issues: Issue[]
  template_applied?: number
  low_confidence_columns?: LowConfidenceColumn[]
  template_id?: string | null
  template_candidates?: { id: string; name: string; score: number; reasons: string[] }[]
}

export const uploadCSV = (file: File): Promise<UploadResponse> => {
  const form = new FormData()
  form.append('file', file)
  return api.post<UploadResponse>('/upload', form).then((r) => r.data)
}

export const getProfile = (id: string) =>
  api.get<{ import_info: ImportInfo; columns: ColumnProfile[]; table_structure: TableStructure }>(`/profile/${id}`).then((r) => r.data)

export const getIssues = (id: string) =>
  api.get<{ issues: Issue[] }>(`/issues/${id}`).then((r) => r.data)

export interface UpdateColumnsResponse {
  columns: ColumnProfile[]
  issues: Issue[]
  low_confidence_columns?: LowConfidenceColumn[]
  inference_metrics?: InferenceMetrics
}

export const updateColumns = (id: string, columns: ColumnProfile[]) =>
  api.put<UpdateColumnsResponse>(`/columns/${id}`, columns).then((r) => r.data)

export interface TemplateInfo {
  signature: string | null
  exists: boolean
  applied: number
  source_filename: string | null
  updated_at: number | null
  low_confidence_columns: LowConfidenceColumn[]
  inference_metrics: InferenceMetrics
}

export const getTemplateInfo = (id: string) =>
  api.get<TemplateInfo>(`/templates/${id}`).then((r) => r.data)

export const saveTemplate = (id: string) =>
  api.post<{ signature: string; n_columns: number }>(`/templates/${id}`).then((r) => r.data)

export const getMetadata = (id: string) =>
  api.get<{ metadata: DatasetMetadata }>(`/metadata/${id}`).then((r) => r.data)

export const saveMetadata = (id: string, metadata: DatasetMetadata) =>
  api.put<{ metadata: DatasetMetadata }>(`/metadata/${id}`, metadata).then((r) => r.data)

export const getFairScore = (id: string): Promise<FAIRScore> =>
  api.get<FAIRScore>(`/fair-score/${id}`).then((r) => r.data)

export const exportUrl = (id: string, type: string) => `/api/export/${id}/${type}`

export const arriveExportUrl = (id: string) => `/api/export/${id}/arrive`

export const prepareExportUrl = (id: string) => `/api/export/${id}/prepare`

export const arriveReportUrl = (id: string) => `/api/export/${id}/arrive-report`

export const prepareReportUrl = (id: string) => `/api/export/${id}/prepare-report`

export const fairReportUrl = (id: string) => `/api/export/${id}/fair-report`

export const extractPaperMetadata = (file: File): Promise<any> => {
  const form = new FormData()
  form.append('file', file)
  return api.post('/paper/extract', form).then((r) => r.data)
}

export const extractPaperMetadataStream = (
  file: File,
  onStatus: (msg: string) => void,
  onResult: (data: any) => void,
  onError: (msg: string) => void,
  signal?: AbortSignal,
): Promise<void> => {
  const form = new FormData()
  form.append('file', file)
  return fetch('/api/paper/extract/stream', { method: 'POST', body: form, signal }).then(async (res) => {
    if (!res.ok) {
      const text = await res.text()
      throw new Error(text)
    }
    const reader = res.body!.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    try {
      while (true) {
        if (signal?.aborted) break
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const event = JSON.parse(line.slice(6))
              if (event.type === 'status') onStatus(event.message)
              else if (event.type === 'result') onResult(event.data)
              else if (event.type === 'error') onError(event.message)
            } catch {}
          }
        }
      }
    } finally {
      reader.cancel()
    }
  })
}

export const buildMetadataPatch = (extraction: {
  dataset_metadata: Record<string, any>
  arrive: Record<string, any>
}): Record<string, any> => {
  const dm = extraction.dataset_metadata
  const patch: Record<string, any> = {}
  const scalar = ['title', 'description', 'creator', 'institution', 'species',
                   'study_type', 'license', 'funding_source', 'protocol_reference']
  for (const key of scalar) {
    if (dm[key] != null) patch[key] = dm[key]
  }
  if (dm.keywords?.length) patch.keywords = dm.keywords
  patch.arrive = extraction.arrive
  return patch
}

export const fetchPaperByDOI = (doi: string): Promise<any> =>
  api.post('/paper/doi', { doi }).then((r) => r.data)

export const storePaperExtraction = (id: string, extraction: any): Promise<void> =>
  api.put(`/paper/${id}/extraction`, extraction).then(() => undefined)

export const getStoredPaperExtraction = (id: string): Promise<any> =>
  api.get(`/paper/${id}/extraction`).then((r) => r.data)

// ── HITL (human-in-the-loop) ─────────────────────────────────────────────

export type HITLCategory =
  | 'column_metadata'
  | 'dataset_metadata'
  | 'fair_recommendation'
  | 'issue_fix'
  | 'schema_extension'

export type HITLStatus =
  | 'pending'
  | 'approved'
  | 'rejected'
  | 'edited'
  | 'applied'
  | 'invalid'
  | 'stale'

export interface HITLSuggestion {
  id: string
  category: HITLCategory
  target: string
  source: string
  confidence: number
  title: string
  rationale: string
  payload: Record<string, any>
  status: HITLStatus
  validation: { ok: boolean; errors: string[] }
  schema_version?: number
  created_at: number
  applied_at: number | null
}

export const getLLMStatus = (): Promise<{ enabled: boolean }> =>
  api.get('/settings/openai-key/status').then((r) => ({ enabled: r.data.configured ?? false }))

export const listHITLSuggestions = (
  id: string,
  filters?: { status?: string; category?: string },
) =>
  api
    .get<{ suggestions: HITLSuggestion[] }>(`/hitl/${id}/suggestions`, { params: filters })
    .then((r) => r.data.suggestions)

export const approveHITLSuggestion = (id: string, sid: string) =>
  api
    .post<{ suggestion: HITLSuggestion; result: any }>(`/hitl/${id}/suggestions/${sid}/approve`)
    .then((r) => r.data)

export const rejectHITLSuggestion = (id: string, sid: string) =>
  api
    .post<{ suggestion: HITLSuggestion }>(`/hitl/${id}/suggestions/${sid}/reject`)
    .then((r) => r.data)

export const editHITLSuggestion = (id: string, sid: string, payload: Record<string, any>) =>
  api
    .put<{ suggestion: HITLSuggestion }>(`/hitl/${id}/suggestions/${sid}`, { payload })
    .then((r) => r.data)

// ── Vocabulary ─────────────────────────────────────────────────────────────

export interface Vocabulary {
  version: number
  validated: boolean
  validated_at: number | null
  column_names: string[]
  semantic_types: string[]
  units: string[]
  metadata_keys: string[]
  licenses: string[]
  study_types: string[]
  controlled_values: Record<string, string[]>
  history: Array<{ version: number; at: number; source: string; added?: Record<string, any> }>
}

export const getVocabulary = (id: string) =>
  api.get<Vocabulary>(`/vocabulary/${id}`).then((r) => r.data)

export const validateVocabulary = (id: string) =>
  api
    .post<{ vocabulary: Vocabulary; marked_stale: number }>(`/vocabulary/${id}/validate`)
    .then((r) => r.data)

export const discoverVocabFromPDF = (
  id: string,
  file: File,
): Promise<{ created: Array<{ key: string; values: string[] }> }> => {
  const form = new FormData()
  form.append('file', file)
  return api
    .post<{ created: Array<{ key: string; values: string[] }> }>(`/vocabulary/${id}/discover-pdf`, form)
    .then((r) => r.data)
}

export const listTemplates = () => api.get('/templates').then((r) => r.data)

export const getTemplate = (tid: string) =>
  api.get(`/templates/registry/${tid}`).then((r) => r.data)

export const uploadTemplate = (body: string, format: 'yaml' | 'json') =>
  api
    .post('/templates', body, {
      headers: {
        'Content-Type': format === 'yaml' ? 'application/x-yaml' : 'application/json',
      },
    })
    .then((r) => r.data)

export const getTemplateSuggestions = (id: string) =>
  api.get(`/${id}/template/suggestions`).then((r) => r.data)

export const assignTemplate = (id: string, tid: string) =>
  api.post(`/${id}/template/${tid}`).then((r) => r.data)

export const unassignTemplate = (id: string) =>
  api.delete(`/${id}/template`).then((r) => r.data)

export const getTemplateValidation = (id: string) =>
  api.get(`/${id}/template/validation`).then((r) => r.data)

export const getPaperTemplateSuggestions = (
  extraction: object,
  additionalTerms: string[] = [],
) =>
  api.post('/templates/paper/suggestions', { extraction, additional_terms: additionalTerms }).then((r) => r.data)

export const suggestPaperSearchTerms = (
  extraction: object,
  currentTerms: string[] = [],
) =>
  api.post('/templates/paper/suggest-terms', { extraction, current_terms: currentTerms }).then((r) => r.data)

export const applyTemplateFromPaper = (id: string, templateId: string) =>
  api.post(`/${id}/template/apply-from-paper`, { template_id: templateId }).then((r) => r.data)

export const generateStarterYaml = (templateId: string, extraction: object) =>
  api
    .post('/templates/paper/generate-yaml', { template_id: templateId, extraction })
    .then((r) => r.data)

export const generateExperimentCsv = (
  templateId: string,
  extraction: object,
  includeFieldIds?: string[],
) =>
  api
    .post('/templates/paper/generate-csv', { template_id: templateId, extraction, include_field_ids: includeFieldIds })
    .then((r) => r.data)

// ── Template Fill ──────────────────────────────────────────────────────────

export interface TemplateCompletionField {
  field_id: string
  label: string
  arrive_section: string | null
  prepare_section: string | null
  severity: 'high' | 'medium' | 'low'
  status: 'satisfied' | 'partial' | 'missing'
  via_crosswalk: boolean
  satisfied_by_field: string | null
  value: string | null
  source: 'direct' | 'crosswalk' | null
  is_column_field: boolean
  prompt: string | null
  paper_hint: string | null
}

export interface TemplateCompletionTotals {
  total: number
  satisfied_direct: number
  satisfied_via_crosswalk: number
  partial: number
  missing: number
}

export interface TemplateCompletionSeverityRow {
  total: number
  satisfied: number
  missing: number
}

export interface TemplateCompletionSection {
  label: string
  kind: 'arrive' | 'prepare'
  total: number
  satisfied: number
  fields: string[]
}

export interface TemplateCompletionReport {
  template_id: string
  template_name: string
  totals: TemplateCompletionTotals
  by_severity: Record<'high' | 'medium' | 'low', TemplateCompletionSeverityRow>
  by_section: TemplateCompletionSection[]
  fields: TemplateCompletionField[]
}

export interface TemplateSuggestion {
  field_id: string
  value: string | null
  rationale: string
  confidence: number
}

export const getTemplateCompletion = (datasetId: string): Promise<TemplateCompletionReport> =>
  api.get<TemplateCompletionReport>(`/${datasetId}/template/completion`).then((r) => r.data)

export const fillTemplateFromPaper = (
  datasetId: string,
): Promise<{ filled: TemplateCompletionField[]; completion: TemplateCompletionReport }> =>
  api
    .post<{ filled: TemplateCompletionField[]; completion: TemplateCompletionReport }>(
      `/${datasetId}/template/fill-from-paper`,
    )
    .then((r) => r.data)

export const llmSuggestTemplate = (
  datasetId: string,
  fieldIds: string[] | null,
): Promise<{ suggestions: TemplateSuggestion[] }> =>
  api
    .post<{ suggestions: TemplateSuggestion[] }>(`/${datasetId}/template/llm-suggest`, {
      field_ids: fieldIds,
    })
    .then((r) => r.data)

export const extractTemplateFromDocument = (
  datasetId: string,
  file: File,
): Promise<{ suggestions: TemplateSuggestion[] }> => {
  const form = new FormData()
  form.append('file', file)
  return api
    .post<{ suggestions: TemplateSuggestion[] }>(
      `/${datasetId}/template/extract-from-document`,
      form,
    )
    .then((r) => r.data)
}

// ── OpenAI settings ─────────────────────────────────────────────────────────

export const getOpenAIKeyStatus = (): Promise<{ configured: boolean; model: string }> =>
  api.get('/settings/openai-key/status').then((r) => r.data)

export const storeOpenAIKey = (apiKey: string): Promise<{ stored: boolean }> =>
  api.post('/settings/openai-key', { api_key: apiKey }).then((r) => r.data)

export const clearOpenAIKey = (): Promise<{ cleared: boolean }> =>
  api.delete('/settings/openai-key').then((r) => r.data)

export const testOpenAIKey = (): Promise<{ ok: boolean; response?: string; error?: string }> =>
  api.post('/settings/openai-key/test').then((r) => r.data)

// ── AI suggestion endpoints ─────────────────────────────────────────────────

export interface AIMetadataSuggestions {
  title_suggestion: string | null
  description_suggestion: string | null
  rationale: string
}

export const previewAIMetadataSuggestions = (id: string) =>
  api.post<{ preview: { sent_fields: any; note: string } }>(`/ai/suggest-metadata/${id}?preview=true`).then((r) => r.data)

export const getAIMetadataSuggestions = (id: string): Promise<{ suggestions: AIMetadataSuggestions }> =>
  api.post(`/ai/suggest-metadata/${id}`).then((r) => r.data)

export const previewAIColumnSuggestions = (id: string) =>
  api.post<{ preview: { sent_fields: any; note: string } }>(`/ai/suggest-columns/${id}?preview=true`).then((r) => r.data)

export const getAIColumnSuggestions = (id: string): Promise<{ suggestions: Record<string, string> }> =>
  api.post(`/ai/suggest-columns/${id}`).then((r) => r.data)

export const previewAIChecklist = (id: string) =>
  api.post<{ preview: { sent_fields: any; note: string } }>(`/ai/suggest-checklist/${id}?preview=true`).then((r) => r.data)

export const getAIChecklist = (id: string): Promise<{ checklist: string }> =>
  api.post(`/ai/suggest-checklist/${id}`).then((r) => r.data)

// ── Assessment-only session ──────────────────────────────────────────────────

export const startAssessmentOnly = (title?: string, description?: string): Promise<{ dataset_id: string; assessment_only: boolean }> =>
  api.post('/assessment-only/start', { title: title ?? '', description: description ?? '' }).then((r) => r.data)

export const importFreeText = (text: string): Promise<any> =>
  api.post('/import/free-text', { text }).then((r) => r.data)

export const startDemoSession = (): Promise<UploadResponse & { demo: boolean }> =>
  api.post('/demo/start').then((r) => r.data)
