// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import CreatorWorkbench from '../screens/CreatorWorkbench'
import { api } from '../api/client'
import type { WorkbenchPack, FileNode } from '../api/client'

vi.mock('@convsim/ui', () => ({
  FormEditor: ({ initialYaml, onChange }: { fileType: string; initialYaml: string; onChange?: (yaml: string) => void }) => (
    <div data-testid="form-editor">
      <textarea
        data-testid="form-editor-yaml"
        aria-label="Form editor YAML"
        defaultValue={initialYaml}
        onChange={(e) => onChange?.(e.target.value)}
      />
    </div>
  ),
}))

vi.mock('../api/client', () => ({
  api: {
    workbench: {
      listPacks: vi.fn(),
      listFiles: vi.fn(),
      readFile: vi.fn(),
      writeFile: vi.fn(),
      validate: vi.fn(),
      copyToLocal: vi.fn(),
      startTestSession: vi.fn(),
      importPack: vi.fn(),
      exportPack: vi.fn(),
    },
    submitTurn: vi.fn(),
    deleteSession: vi.fn(),
  },
}))

const OFFICIAL_PACK: WorkbenchPack = {
  kind: 'official',
  slug: 'job-interview',
  pack_id: 'official.job_interview',
  name: 'Job Interview',
  editable: false,
}

const LOCAL_PACK: WorkbenchPack = {
  kind: 'local-dev',
  slug: 'my-pack',
  pack_id: 'local.my_pack',
  name: 'My Pack',
  editable: true,
}

const MOCK_TREE: FileNode[] = [
  { name: 'manifest.yaml', path: 'manifest.yaml', kind: 'yaml' },
  { name: 'README.md', path: 'README.md', kind: 'markdown' },
  {
    name: 'scenarios',
    path: 'scenarios',
    kind: 'dir',
    children: [{ name: 'basic.yaml', path: 'scenarios/basic.yaml', kind: 'yaml' }],
  },
  { name: 'logo.png', path: 'logo.png', kind: 'other' },
]

const MANIFEST_CONTENT = 'schema_version: "0.1"\npack_id: official.job_interview\nname: Job Interview\n'

const TEST_SESSION_RESPONSE = {
  session_id: 'test-abc123',
  state: 'PlayerTurnListening',
  npc_opening: 'Ready to test. Send a message to begin.',
  state_vars: { trust: 50, patience: 75, pressure: 25, rapport: 50, openness: 50, objective_progress: 0 },
}

const TURN_RESPONSE = {
  session_id: 'test-abc123',
  state: 'PlayerTurnListening',
  events: [
    {
      event_id: 1,
      session_id: 'test-abc123',
      event_type: 'player_turn',
      payload: { content: 'Hello there.' },
      created_at: '2026-01-01T00:00:00Z',
    },
    {
      event_id: 2,
      session_id: 'test-abc123',
      event_type: 'npc_turn',
      payload: {
        content: 'Hello! I am a simulated NPC.',
        emotion: 'neutral',
        state_delta: { trust: 5 },
        event_flags: [],
        safety: { status: 'ok' },
        ending_type: null,
      },
      created_at: '2026-01-01T00:00:01Z',
    },
  ],
}

function renderWorkbench() {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <CreatorWorkbench />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.mocked(api.workbench.listPacks).mockResolvedValue({ ok: true, data: [OFFICIAL_PACK, LOCAL_PACK] })
  vi.mocked(api.workbench.listFiles).mockResolvedValue({ ok: true, data: { tree: [] } })
  vi.mocked(api.workbench.readFile).mockResolvedValue({ ok: true, data: { content: '', editable: false } })
  vi.mocked(api.workbench.writeFile).mockResolvedValue({ ok: true, data: { ok: true, validation: null } })
  vi.mocked(api.workbench.validate).mockResolvedValue({ ok: true, data: { valid: true, errors: [], warnings: [] } })
  vi.mocked(api.workbench.copyToLocal).mockResolvedValue({ ok: true, data: LOCAL_PACK })
  vi.mocked(api.workbench.startTestSession).mockResolvedValue({ ok: true, data: TEST_SESSION_RESPONSE })
  vi.mocked(api.workbench.importPack).mockResolvedValue({ ok: true, data: LOCAL_PACK })
  vi.mocked(api.workbench.exportPack).mockResolvedValue({ ok: true, data: { blob: new Blob([]), filename: 'pack.zip' } })
  vi.mocked(api.submitTurn).mockResolvedValue({ ok: true, data: TURN_RESPONSE })
  vi.mocked(api.deleteSession).mockResolvedValue({ ok: true, data: undefined })
})

describe('CreatorWorkbench', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders the heading', () => {
    renderWorkbench()
    expect(screen.getByRole('heading', { name: /creator workbench/i })).toBeInTheDocument()
  })

  it('shows pack list after loading', async () => {
    renderWorkbench()
    expect(await screen.findByText('Job Interview')).toBeInTheDocument()
    expect(await screen.findByText('My Pack')).toBeInTheDocument()
  })

  it('shows official label for official packs', async () => {
    renderWorkbench()
    await screen.findByText('Job Interview')
    expect(screen.getByText('official')).toBeInTheDocument()
  })

  it('shows file tree when a pack is selected', async () => {
    vi.mocked(api.workbench.listFiles).mockResolvedValue({ ok: true, data: { tree: MOCK_TREE } })

    renderWorkbench()
    const packBtn = await screen.findByRole('button', { name: /job interview/i })
    fireEvent.click(packBtn)

    await waitFor(() => {
      expect(screen.getByRole('tree')).toBeInTheDocument()
    })
  })

  it('shows file content when a YAML file is selected', async () => {
    vi.mocked(api.workbench.listFiles).mockResolvedValue({ ok: true, data: { tree: MOCK_TREE } })
    vi.mocked(api.workbench.readFile).mockResolvedValue({ ok: true, data: { content: MANIFEST_CONTENT, editable: false } })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /job interview/i }))

    const fileBtn = await screen.findByRole('button', { name: /open manifest\.yaml/i })
    fireEvent.click(fileBtn)

    await waitFor(() => {
      const editor = screen.getByTestId('file-editor') as HTMLTextAreaElement
      expect(editor.value).toContain('pack_id')
    })
  })

  it('shows read-only badge for official pack file', async () => {
    vi.mocked(api.workbench.listFiles).mockResolvedValue({ ok: true, data: { tree: MOCK_TREE } })
    vi.mocked(api.workbench.readFile).mockResolvedValue({ ok: true, data: { content: MANIFEST_CONTENT, editable: false } })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /job interview/i }))
    fireEvent.click(await screen.findByRole('button', { name: /open manifest\.yaml/i }))

    await waitFor(() => {
      expect(screen.getByTestId('read-only-badge')).toBeInTheDocument()
    })
  })

  it('shows create-local-copy button for read-only files', async () => {
    vi.mocked(api.workbench.listFiles).mockResolvedValue({ ok: true, data: { tree: MOCK_TREE } })
    vi.mocked(api.workbench.readFile).mockResolvedValue({ ok: true, data: { content: MANIFEST_CONTENT, editable: false } })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /job interview/i }))
    fireEvent.click(await screen.findByRole('button', { name: /open manifest\.yaml/i }))

    await waitFor(() => {
      expect(screen.getByTestId('copy-to-local-button')).toBeInTheDocument()
    })
  })

  it('shows no save button for read-only official pack', async () => {
    vi.mocked(api.workbench.listFiles).mockResolvedValue({ ok: true, data: { tree: MOCK_TREE } })
    vi.mocked(api.workbench.readFile).mockResolvedValue({ ok: true, data: { content: MANIFEST_CONTENT, editable: false } })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /job interview/i }))
    fireEvent.click(await screen.findByRole('button', { name: /open manifest\.yaml/i }))

    await waitFor(() => {
      expect(screen.queryByTestId('save-button')).not.toBeInTheDocument()
    })
  })

  it('shows editable textarea and save button for local-dev pack', async () => {
    const localContent = 'name: My Pack\n'
    vi.mocked(api.workbench.listFiles).mockResolvedValue({ ok: true, data: { tree: MOCK_TREE } })
    vi.mocked(api.workbench.readFile).mockResolvedValue({ ok: true, data: { content: localContent, editable: true } })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /my pack/i }))
    fireEvent.click(await screen.findByRole('button', { name: /open manifest\.yaml/i }))

    await waitFor(() => {
      expect(screen.getByTestId('save-button')).toBeInTheDocument()
      expect(screen.queryByTestId('read-only-badge')).not.toBeInTheDocument()
    })
  })

  it('shows dirty indicator after editing content', async () => {
    const localContent = 'name: My Pack\n'
    vi.mocked(api.workbench.listFiles).mockResolvedValue({ ok: true, data: { tree: MOCK_TREE } })
    vi.mocked(api.workbench.readFile).mockResolvedValue({ ok: true, data: { content: localContent, editable: true } })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /my pack/i }))
    fireEvent.click(await screen.findByRole('button', { name: /open manifest\.yaml/i }))

    await waitFor(() => {
      expect(screen.getByTestId('file-editor')).toBeInTheDocument()
    })

    fireEvent.change(screen.getByTestId('file-editor'), {
      target: { value: 'name: Changed\n' },
    })

    expect(screen.getByTestId('dirty-indicator')).toBeInTheDocument()
  })

  it('clears dirty state after saving', async () => {
    const localContent = 'name: My Pack\n'
    vi.mocked(api.workbench.listFiles).mockResolvedValue({ ok: true, data: { tree: MOCK_TREE } })
    vi.mocked(api.workbench.readFile).mockResolvedValue({ ok: true, data: { content: localContent, editable: true } })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /my pack/i }))
    fireEvent.click(await screen.findByRole('button', { name: /open manifest\.yaml/i }))
    await waitFor(() => expect(screen.getByTestId('file-editor')).toBeInTheDocument())

    fireEvent.change(screen.getByTestId('file-editor'), {
      target: { value: 'name: Changed\n' },
    })
    expect(screen.getByTestId('dirty-indicator')).toBeInTheDocument()

    fireEvent.click(screen.getByTestId('save-button'))

    await waitFor(() => {
      expect(screen.queryByTestId('dirty-indicator')).not.toBeInTheDocument()
    })
    expect(vi.mocked(api.workbench.writeFile)).toHaveBeenCalledOnce()
  })

  it('shows unsupported label for non-text files in tree', async () => {
    vi.mocked(api.workbench.listFiles).mockResolvedValue({ ok: true, data: { tree: MOCK_TREE } })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /job interview/i }))

    await waitFor(() => {
      expect(screen.getByText('unsupported')).toBeInTheDocument()
    })
  })

  it('shows pack error when API fails', async () => {
    vi.mocked(api.workbench.listPacks).mockResolvedValue({ ok: false, error: { kind: 'network', message: 'Connection refused' } })

    renderWorkbench()

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
  })

  it('copy-to-local button triggers copy and switches to new pack', async () => {
    const newPack: WorkbenchPack = { kind: 'local-dev', slug: 'job-interview-copy', pack_id: 'local.job_interview_copy', name: 'Job Interview', editable: true }
    vi.mocked(api.workbench.listFiles).mockResolvedValue({ ok: true, data: { tree: MOCK_TREE } })
    vi.mocked(api.workbench.readFile).mockResolvedValue({ ok: true, data: { content: MANIFEST_CONTENT, editable: false } })
    vi.mocked(api.workbench.copyToLocal).mockResolvedValue({ ok: true, data: newPack })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /job interview/i }))
    fireEvent.click(await screen.findByRole('button', { name: /open manifest\.yaml/i }))

    const copyBtn = await screen.findByTestId('copy-to-local-button')
    fireEvent.click(copyBtn)

    await waitFor(() => {
      expect(vi.mocked(api.workbench.copyToLocal)).toHaveBeenCalledOnce()
    })

    // After copy, the file editor should be cleared (no file selected)
    await waitFor(() => {
      expect(screen.queryByTestId('file-editor')).not.toBeInTheDocument()
    })
  })

  it('shows a valid badge when the pack validates cleanly', async () => {
    vi.mocked(api.workbench.listFiles).mockResolvedValue({ ok: true, data: { tree: MOCK_TREE } })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /my pack/i }))

    await waitFor(() => {
      expect(screen.getByTestId('validation-panel')).toHaveTextContent(/valid/i)
    })
  })

  it('lists validation errors when the pack is invalid', async () => {
    vi.mocked(api.workbench.listFiles).mockResolvedValue({ ok: true, data: { tree: MOCK_TREE } })
    vi.mocked(api.workbench.validate).mockResolvedValue({ ok: true, data: {
      valid: false,
      errors: [
        { severity: 'error', rule_id: 'SCHEMA_VIOLATION', file: 'manifest.yaml', pointer: '/author', message: "'author' is a required property", suggested_fix: 'Add author' },
      ],
      warnings: [],
    } })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /my pack/i }))

    await waitFor(() => {
      const panel = screen.getByTestId('validation-panel')
      expect(panel).toHaveTextContent(/1 validation error/i)
      expect(panel).toHaveTextContent(/required property/i)
    })
  })

  it('refreshes validation from the save response', async () => {
    const localContent = 'name: My Pack\n'
    vi.mocked(api.workbench.listFiles).mockResolvedValue({ ok: true, data: { tree: MOCK_TREE } })
    vi.mocked(api.workbench.readFile).mockResolvedValue({ ok: true, data: { content: localContent, editable: true } })
    vi.mocked(api.workbench.writeFile).mockResolvedValue({ ok: true, data: {
      ok: true,
      validation: {
        valid: false,
        errors: [
          { severity: 'error', rule_id: 'INVALID_MANIFEST_YAML', file: 'manifest.yaml', pointer: '', message: 'manifest.yaml must be a YAML mapping', suggested_fix: 'Fix YAML' },
        ],
        warnings: [],
      },
    } })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /my pack/i }))
    fireEvent.click(await screen.findByRole('button', { name: /open manifest\.yaml/i }))
    await waitFor(() => expect(screen.getByTestId('file-editor')).toBeInTheDocument())

    // Pack initially validates clean.
    await waitFor(() => expect(screen.getByTestId('validation-panel')).toHaveTextContent(/valid/i))

    fireEvent.change(screen.getByTestId('file-editor'), { target: { value: 'broken: [' } })
    fireEvent.click(screen.getByTestId('save-button'))

    // After save, the validation panel reflects the newly-returned errors.
    await waitFor(() => {
      expect(screen.getByTestId('validation-panel')).toHaveTextContent(/must be a YAML mapping/i)
    })
  })

  it('clears a prior service error when a save returns fresh validation', async () => {
    const localContent = 'name: My Pack\n'
    vi.mocked(api.workbench.listFiles).mockResolvedValue({ ok: true, data: { tree: MOCK_TREE } })
    vi.mocked(api.workbench.readFile).mockResolvedValue({ ok: true, data: { content: localContent, editable: true } })
    // Initial on-select validation fails: the validator is down.
    vi.mocked(api.workbench.validate).mockResolvedValue({ ok: false, error: { kind: 'network', message: 'boom' } })
    // Save returns a clean validation once the validator has recovered.
    vi.mocked(api.workbench.writeFile).mockResolvedValue({ ok: true, data: {
      ok: true,
      validation: { valid: true, errors: [], warnings: [] },
    } })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /my pack/i }))
    fireEvent.click(await screen.findByRole('button', { name: /open manifest\.yaml/i }))
    await waitFor(() => expect(screen.getByTestId('file-editor')).toBeInTheDocument())

    // Panel first reports the validator is unavailable.
    await waitFor(() =>
      expect(screen.getByTestId('validation-panel')).toHaveTextContent(/validator unavailable/i),
    )

    fireEvent.change(screen.getByTestId('file-editor'), { target: { value: 'name: Fixed\n' } })
    fireEvent.click(screen.getByTestId('save-button'))

    // The fresh, valid save result must replace the stale service error.
    await waitFor(() => {
      const panel = screen.getByTestId('validation-panel')
      expect(panel).toHaveTextContent(/pack is valid/i)
      expect(panel).not.toHaveTextContent(/validator unavailable/i)
    })
  })

  it('groups validation errors by file', async () => {
    vi.mocked(api.workbench.listFiles).mockResolvedValue({ ok: true, data: { tree: MOCK_TREE } })
    vi.mocked(api.workbench.validate).mockResolvedValue({ ok: true, data: {
      valid: false,
      errors: [
        { severity: 'error', rule_id: 'SCHEMA_VIOLATION', file: 'manifest.yaml', pointer: '/author', message: 'author is required', suggested_fix: 'Add author field' },
        { severity: 'error', rule_id: 'SCHEMA_VIOLATION', file: 'scenarios/basic.yaml', pointer: '/summary', message: 'summary is required', suggested_fix: 'Add summary' },
      ],
      warnings: [],
    } })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /my pack/i }))

    await waitFor(() => {
      const panel = screen.getByTestId('validation-panel')
      expect(panel).toHaveTextContent('manifest.yaml')
      expect(panel).toHaveTextContent('scenarios/basic.yaml')
      expect(panel).toHaveTextContent('author is required')
      expect(panel).toHaveTextContent('summary is required')
    })
  })

  it('shows a clickable file link for yaml findings', async () => {
    vi.mocked(api.workbench.listFiles).mockResolvedValue({ ok: true, data: { tree: MOCK_TREE } })
    vi.mocked(api.workbench.validate).mockResolvedValue({ ok: true, data: {
      valid: false,
      errors: [
        { severity: 'error', rule_id: 'SCHEMA_VIOLATION', file: 'manifest.yaml', pointer: '/author', message: 'author is required', suggested_fix: 'Add author' },
      ],
      warnings: [],
    } })
    vi.mocked(api.workbench.readFile).mockResolvedValue({ ok: true, data: { content: 'pack_id: x\n', editable: true } })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /my pack/i }))

    const fileLink = await screen.findByTestId('validation-file-link-manifest.yaml')
    expect(fileLink).toBeInTheDocument()

    // Clicking the file link should open the file in the editor
    fireEvent.click(fileLink)
    await waitFor(() => {
      expect(screen.getByTestId('file-editor')).toBeInTheDocument()
    })
  })

  it('shows security badge and SECURITY label for forbidden file findings', async () => {
    vi.mocked(api.workbench.listFiles).mockResolvedValue({ ok: true, data: { tree: MOCK_TREE } })
    vi.mocked(api.workbench.validate).mockResolvedValue({ ok: true, data: {
      valid: false,
      errors: [
        { severity: 'error', rule_id: 'FORBIDDEN_FILE', file: 'run.sh', pointer: '', message: "Executable file not allowed: 'run.sh'", suggested_fix: 'Remove this file', category: 'security' },
      ],
      warnings: [],
    } })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /my pack/i }))

    await waitFor(() => {
      const panel = screen.getByTestId('validation-panel')
      expect(panel).toHaveTextContent('SECURITY')
      expect(screen.getByTestId('security-badge')).toBeInTheDocument()
    })
  })

  it('shows suggested fix text for each finding', async () => {
    vi.mocked(api.workbench.listFiles).mockResolvedValue({ ok: true, data: { tree: MOCK_TREE } })
    vi.mocked(api.workbench.validate).mockResolvedValue({ ok: true, data: {
      valid: false,
      errors: [
        { severity: 'error', rule_id: 'SCHEMA_VIOLATION', file: 'manifest.yaml', pointer: '/author', message: 'author required', suggested_fix: 'Add the author field to manifest.yaml' },
      ],
      warnings: [],
    } })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /my pack/i }))

    await waitFor(() => {
      expect(screen.getByTestId('validation-panel')).toHaveTextContent('Add the author field to manifest.yaml')
    })
  })

  // ---------------------------------------------------------------------------
  // Import / Export
  // ---------------------------------------------------------------------------

  it('shows import pack button in pack list', async () => {
    renderWorkbench()
    expect(await screen.findByTestId('import-pack-button')).toBeInTheDocument()
  })

  it('shows export pack button when a pack is selected', async () => {
    vi.mocked(api.workbench.listFiles).mockResolvedValue({ ok: true, data: { tree: MOCK_TREE } })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /my pack/i }))

    await waitFor(() => {
      expect(screen.getByTestId('export-pack-button')).toBeInTheDocument()
    })
  })

  it('import success adds new pack to list and shows it as selected', async () => {
    const newPack: WorkbenchPack = { kind: 'local-dev', slug: 'imported-pack', pack_id: 'local.imported_pack', name: 'Imported Pack', editable: true }
    vi.mocked(api.workbench.importPack).mockResolvedValue({ ok: true, data: newPack })

    renderWorkbench()
    await screen.findByTestId('import-pack-button')

    // Simulate file input change via the hidden input
    const fileInput = screen.getByTestId('import-file-input') as HTMLInputElement
    const zipFile = new File(['PK\x03\x04'], 'my-pack.zip', { type: 'application/zip' })
    Object.defineProperty(fileInput, 'files', { value: [zipFile], writable: false })
    fireEvent.change(fileInput)

    await waitFor(() => {
      expect(vi.mocked(api.workbench.importPack)).toHaveBeenCalledOnce()
    })
  })

  it('import with slug conflict shows the rename notice', async () => {
    const renamedPack = { kind: 'local-dev' as const, slug: 'local.imported_pack-2', pack_id: 'local.imported_pack', name: 'Imported Pack', editable: true, renamed_from: 'local.imported_pack' }
    vi.mocked(api.workbench.importPack).mockResolvedValue({ ok: true, data: renamedPack })

    renderWorkbench()
    await screen.findByTestId('import-pack-button')

    const fileInput = screen.getByTestId('import-file-input') as HTMLInputElement
    const zipFile = new File(['PK\x03\x04'], 'dup.zip', { type: 'application/zip' })
    Object.defineProperty(fileInput, 'files', { value: [zipFile], writable: false })
    fireEvent.change(fileInput)

    // The rename notice must survive the pack-selection that follows a
    // successful import (handleSelectPack resets import notices).
    await waitFor(() => {
      expect(screen.getByTestId('import-renamed-notice')).toBeInTheDocument()
      expect(screen.getByTestId('import-renamed-notice')).toHaveTextContent('local.imported_pack-2')
    })
  })

  it('import validation failure shows errors without crashing', async () => {
    vi.mocked(api.workbench.importPack).mockResolvedValue({ ok: true, data: {
      kind: 'validation',
      valid: false,
      errors: [
        { severity: 'error', rule_id: 'SCHEMA_VIOLATION', file: 'manifest.yaml', pointer: '/author', message: 'author is required', suggested_fix: 'Add author' },
      ],
      warnings: [],
    } })

    renderWorkbench()
    await screen.findByTestId('import-pack-button')

    const fileInput = screen.getByTestId('import-file-input') as HTMLInputElement
    const zipFile = new File(['PK\x03\x04'], 'bad.zip', { type: 'application/zip' })
    Object.defineProperty(fileInput, 'files', { value: [zipFile], writable: false })
    fireEvent.change(fileInput)

    await waitFor(() => {
      expect(screen.getByTestId('import-validation-errors')).toBeInTheDocument()
      expect(screen.getByTestId('import-validation-errors')).toHaveTextContent(/author is required/i)
    })
  })

  it('import of a corrupt/unsafe zip shows an error instead of crashing', async () => {
    // Corrupt zip and zip-slip rejections come back as an http-error. The UI must render
    // this as an error, not crash trying to map over undefined errors.
    vi.mocked(api.workbench.importPack).mockResolvedValue({ ok: false, error: { kind: 'http-error', message: 'Uploaded file is not a valid .zip archive', status: 422 } })

    renderWorkbench()
    await screen.findByTestId('import-pack-button')

    const fileInput = screen.getByTestId('import-file-input') as HTMLInputElement
    const zipFile = new File(['not a zip'], 'corrupt.zip', { type: 'application/zip' })
    Object.defineProperty(fileInput, 'files', { value: [zipFile], writable: false })
    fireEvent.change(fileInput)

    await waitFor(() => {
      expect(screen.getByTestId('import-error')).toBeInTheDocument()
    })
    expect(screen.queryByTestId('import-validation-errors')).not.toBeInTheDocument()
  })

  it('export success shows filename confirmation', async () => {
    const zipBlob = new Blob(['PK\x03\x04'], { type: 'application/zip' })

    // jsdom does not implement URL.createObjectURL, so vi.spyOn can't wrap a
    // non-existent method — define the property directly so triggerDownload
    // doesn't throw.
    const createObjectURL = vi.fn().mockReturnValue('blob:test')
    const revokeObjectURL = vi.fn()
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeObjectURL })

    vi.mocked(api.workbench.listFiles).mockResolvedValue({ ok: true, data: { tree: MOCK_TREE } })
    vi.mocked(api.workbench.exportPack).mockResolvedValue({ ok: true, data: { blob: zipBlob, filename: 'my-pack-0.1.0.zip' } })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /my pack/i }))

    const exportBtn = await screen.findByTestId('export-pack-button')
    fireEvent.click(exportBtn)

    await waitFor(() => {
      expect(screen.getByTestId('export-success')).toBeInTheDocument()
      expect(screen.getByTestId('export-success')).toHaveTextContent('my-pack-0.1.0.zip')
    })
  })

  it('export validation failure shows error message', async () => {
    vi.mocked(api.workbench.listFiles).mockResolvedValue({ ok: true, data: { tree: MOCK_TREE } })
    vi.mocked(api.workbench.exportPack).mockResolvedValue({ ok: false, error: { kind: 'http-error', message: 'Export blocked: name is required (SCHEMA_VIOLATION)', status: 422 } })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /my pack/i }))
    fireEvent.click(await screen.findByTestId('export-pack-button'))

    await waitFor(() => {
      expect(screen.getByTestId('export-error')).toBeInTheDocument()
    })
  })

  it('shows links to authoring docs alongside findings', async () => {
    vi.mocked(api.workbench.listFiles).mockResolvedValue({ ok: true, data: { tree: MOCK_TREE } })
    vi.mocked(api.workbench.validate).mockResolvedValue({ ok: true, data: {
      valid: false,
      errors: [
        { severity: 'error', rule_id: 'SCHEMA_VIOLATION', file: 'manifest.yaml', pointer: '/author', message: 'author required', suggested_fix: 'See the authoring guide' },
      ],
      warnings: [],
    } })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /my pack/i }))

    const guideLink = await screen.findByRole('link', { name: /authoring guide/i })
    expect(guideLink).toHaveAttribute('href', expect.stringContaining('scenario-authoring'))
    expect(screen.getByRole('link', { name: /validation rules/i })).toBeInTheDocument()
  })

  it('shows copy validation button', async () => {
    vi.mocked(api.workbench.listFiles).mockResolvedValue({ ok: true, data: { tree: MOCK_TREE } })
    vi.mocked(api.workbench.validate).mockResolvedValue({ ok: true, data: {
      valid: false,
      errors: [
        { severity: 'error', rule_id: 'SCHEMA_VIOLATION', file: 'manifest.yaml', pointer: '/author', message: 'author required', suggested_fix: 'Fix it' },
      ],
      warnings: [],
    } })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /my pack/i }))

    await waitFor(() => {
      expect(screen.getByTestId('copy-validation-button')).toBeInTheDocument()
    })
  })

  it('shows service error when validator API fails', async () => {
    vi.mocked(api.workbench.listFiles).mockResolvedValue({ ok: true, data: { tree: MOCK_TREE } })
    vi.mocked(api.workbench.validate).mockResolvedValue({ ok: false, error: { kind: 'http-error', message: 'Internal server error', status: 500 } })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /my pack/i }))

    await waitFor(() => {
      const panel = screen.getByTestId('validation-panel')
      expect(panel).toHaveTextContent(/validator unavailable/i)
    })
  })

  it('clears dirty state immediately when switching to a different file', async () => {
    const localContent = 'name: My Pack\n'
    // jsdom doesn't implement window.confirm; stub it to return true (user confirms discard)
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(true))

    vi.mocked(api.workbench.listFiles).mockResolvedValue({ ok: true, data: { tree: MOCK_TREE } })
    vi.mocked(api.workbench.readFile).mockResolvedValue({ ok: true, data: { content: localContent, editable: true } })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /my pack/i }))
    fireEvent.click(await screen.findByRole('button', { name: /open manifest\.yaml/i }))
    await waitFor(() => expect(screen.getByTestId('file-editor')).toBeInTheDocument())

    // Make the editor dirty
    fireEvent.change(screen.getByTestId('file-editor'), { target: { value: 'name: Changed\n' } })
    expect(screen.getByTestId('dirty-indicator')).toBeInTheDocument()

    // Switch to another file — dirty state must clear immediately (not wait for load to finish)
    fireEvent.click(await screen.findByRole('button', { name: /open README\.md/i }))

    await waitFor(() => {
      expect(screen.queryByTestId('dirty-indicator')).not.toBeInTheDocument()
    })
  })
})

// ---------------------------------------------------------------------------
// Test Chat Panel
// ---------------------------------------------------------------------------

describe('CreatorWorkbench — Test Chat', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('shows Edit and Test Chat tabs when a pack is selected', async () => {
    vi.mocked(api.workbench.listFiles).mockResolvedValue({ ok: true, data: { tree: MOCK_TREE } })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /my pack/i }))

    await waitFor(() => {
      expect(screen.getByTestId('tab-edit')).toBeInTheDocument()
      expect(screen.getByTestId('tab-test')).toBeInTheDocument()
    })
  })

  it('does not show tabs when no pack is selected', () => {
    renderWorkbench()
    expect(screen.queryByTestId('tab-edit')).not.toBeInTheDocument()
    expect(screen.queryByTestId('tab-test')).not.toBeInTheDocument()
  })

  it('switches to Test Chat tab and shows Start Test button', async () => {
    vi.mocked(api.workbench.listFiles).mockResolvedValue({ ok: true, data: { tree: MOCK_TREE } })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /my pack/i }))
    await waitFor(() => expect(screen.getByTestId('tab-test')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('tab-test'))

    await waitFor(() => {
      expect(screen.getByTestId('start-test-btn')).toBeInTheDocument()
    })
  })

  it('shows validation error message and disables Start Test when pack has errors', async () => {
    vi.mocked(api.workbench.listFiles).mockResolvedValue({ ok: true, data: { tree: MOCK_TREE } })
    vi.mocked(api.workbench.validate).mockResolvedValue({ ok: true, data: {
      valid: false,
      errors: [{ severity: 'error', rule_id: 'SCHEMA_VIOLATION', file: 'manifest.yaml', pointer: '/name', message: 'name is required', suggested_fix: 'Add name' }],
      warnings: [],
    } })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /my pack/i }))
    await waitFor(() => expect(screen.getByTestId('tab-test')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('tab-test'))

    await waitFor(() => {
      expect(screen.getByTestId('test-chat-validation-error')).toBeInTheDocument()
      expect(screen.getByTestId('start-test-btn')).toBeDisabled()
    })
  })

  it('starts a test session and shows NPC opening in transcript', async () => {
    vi.mocked(api.workbench.listFiles).mockResolvedValue({ ok: true, data: { tree: MOCK_TREE } })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /my pack/i }))
    await waitFor(() => expect(screen.getByTestId('tab-test')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('tab-test'))
    fireEvent.click(await screen.findByTestId('start-test-btn'))

    await waitFor(() => {
      expect(screen.getByTestId('test-transcript')).toBeInTheDocument()
      expect(screen.getByText('Ready to test. Send a message to begin.')).toBeInTheDocument()
    })
    expect(vi.mocked(api.workbench.startTestSession)).toHaveBeenCalledOnce()
  })

  it('shows state inspector with initial state variables after start', async () => {
    vi.mocked(api.workbench.listFiles).mockResolvedValue({ ok: true, data: { tree: MOCK_TREE } })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /my pack/i }))
    fireEvent.click(await screen.findByTestId('tab-test'))
    fireEvent.click(await screen.findByTestId('start-test-btn'))

    await waitFor(() => {
      expect(screen.getByTestId('state-inspector')).toBeInTheDocument()
      expect(screen.getByTestId('state-inspector')).toHaveTextContent('trust')
      expect(screen.getByTestId('state-inspector')).toHaveTextContent('50')
    })
  })

  it('submits a message and adds player and NPC entries to transcript', async () => {
    vi.mocked(api.workbench.listFiles).mockResolvedValue({ ok: true, data: { tree: MOCK_TREE } })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /my pack/i }))
    fireEvent.click(await screen.findByTestId('tab-test'))
    fireEvent.click(await screen.findByTestId('start-test-btn'))

    await waitFor(() => screen.findByTestId('test-chat-input'))

    fireEvent.change(screen.getByTestId('test-chat-input'), { target: { value: 'Hello there.' } })
    fireEvent.click(screen.getByTestId('send-test-btn'))

    await waitFor(() => {
      expect(screen.getByText('Hello there.')).toBeInTheDocument()
      expect(screen.getByText('Hello! I am a simulated NPC.')).toBeInTheDocument()
    })
    expect(vi.mocked(api.submitTurn)).toHaveBeenCalledOnce()
  })

  it('shows state delta indicators after a turn with non-zero delta', async () => {
    vi.mocked(api.workbench.listFiles).mockResolvedValue({ ok: true, data: { tree: MOCK_TREE } })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /my pack/i }))
    fireEvent.click(await screen.findByTestId('tab-test'))
    fireEvent.click(await screen.findByTestId('start-test-btn'))
    await screen.findByTestId('test-chat-input')

    fireEvent.change(screen.getByTestId('test-chat-input'), { target: { value: 'test' } })
    fireEvent.click(screen.getByTestId('send-test-btn'))

    // state_delta has { trust: 5 }, so a +5 indicator should appear
    await waitFor(() => {
      expect(screen.getByTestId('state-delta')).toHaveTextContent('+5')
    })
  })

  it('discard button calls DELETE and returns to idle state', async () => {
    vi.mocked(api.workbench.listFiles).mockResolvedValue({ ok: true, data: { tree: MOCK_TREE } })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /my pack/i }))
    fireEvent.click(await screen.findByTestId('tab-test'))
    fireEvent.click(await screen.findByTestId('start-test-btn'))

    await waitFor(() => screen.findByTestId('discard-test-btn'))
    fireEvent.click(screen.getByTestId('discard-test-btn'))

    await waitFor(() => {
      expect(screen.getByTestId('start-test-btn')).toBeInTheDocument()
    })
    expect(vi.mocked(api.deleteSession)).toHaveBeenCalledOnce()
  })

  it('reset button discards current session and starts a new one', async () => {
    const startCount = { n: 0 }
    vi.mocked(api.workbench.listFiles).mockResolvedValue({ ok: true, data: { tree: MOCK_TREE } })
    vi.mocked(api.workbench.startTestSession).mockImplementation(() => {
      startCount.n++
      return Promise.resolve({ ok: true as const, data: { ...TEST_SESSION_RESPONSE, session_id: `test-${startCount.n}` } })
    })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /my pack/i }))
    fireEvent.click(await screen.findByTestId('tab-test'))
    fireEvent.click(await screen.findByTestId('start-test-btn'))

    await waitFor(() => screen.findByTestId('reset-test-btn'))
    fireEvent.click(screen.getByTestId('reset-test-btn'))

    await waitFor(() => {
      expect(startCount.n).toBe(2)
    })
  })

  it('session ended banner appears when state transitions to Ended', async () => {
    const endedTurnResponse = {
      ...TURN_RESPONSE,
      state: 'Ended',
      events: [
        TURN_RESPONSE.events[0],
        {
          ...TURN_RESPONSE.events[1],
          payload: { ...TURN_RESPONSE.events[1].payload, ending_type: 'timeout', safety: { status: 'ok' } },
        },
      ],
    }
    vi.mocked(api.workbench.listFiles).mockResolvedValue({ ok: true, data: { tree: MOCK_TREE } })
    vi.mocked(api.submitTurn).mockResolvedValue({ ok: true, data: endedTurnResponse })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /my pack/i }))
    fireEvent.click(await screen.findByTestId('tab-test'))
    fireEvent.click(await screen.findByTestId('start-test-btn'))
    await screen.findByTestId('test-chat-input')

    fireEvent.change(screen.getByTestId('test-chat-input'), { target: { value: 'last message' } })
    fireEvent.click(screen.getByTestId('send-test-btn'))

    await waitFor(() => {
      expect(screen.getByTestId('session-ended-banner')).toBeInTheDocument()
      expect(screen.getByTestId('session-ended-banner')).toHaveTextContent(/timeout/i)
    })
  })

  it('switching back to Edit tab preserves editor state', async () => {
    const localContent = 'name: My Pack\n'
    vi.mocked(api.workbench.listFiles).mockResolvedValue({ ok: true, data: { tree: MOCK_TREE } })
    vi.mocked(api.workbench.readFile).mockResolvedValue({ ok: true, data: { content: localContent, editable: true } })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /my pack/i }))
    fireEvent.click(await screen.findByRole('button', { name: /open manifest\.yaml/i }))
    await waitFor(() => expect(screen.getByTestId('file-editor')).toBeInTheDocument())

    // Switch to test tab then back to edit tab
    fireEvent.click(screen.getByTestId('tab-test'))
    fireEvent.click(screen.getByTestId('tab-edit'))

    // Editor should still be present with the same content
    await waitFor(() => {
      const editor = screen.getByTestId('file-editor') as HTMLTextAreaElement
      expect(editor.value).toContain('name: My Pack')
    })
  })

  it('shows form editor mode toggle for editable recognized YAML files', async () => {
    const localContent = 'pack_id: local.my_pack\nname: My Pack\n'
    vi.mocked(api.workbench.listFiles).mockResolvedValue({ ok: true, data: { tree: MOCK_TREE } })
    vi.mocked(api.workbench.readFile).mockResolvedValue({ ok: true, data: { content: localContent, editable: true } })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /my pack/i }))
    fireEvent.click(await screen.findByRole('button', { name: /open manifest\.yaml/i }))

    await waitFor(() => {
      expect(screen.getByTestId('editor-mode-toggle')).toBeInTheDocument()
      expect(screen.getByTestId('editor-mode-yaml')).toBeInTheDocument()
      expect(screen.getByTestId('editor-mode-form')).toBeInTheDocument()
    })
  })

  it('switches to form editor when form mode button is clicked', async () => {
    const localContent = 'pack_id: local.my_pack\nname: My Pack\n'
    vi.mocked(api.workbench.listFiles).mockResolvedValue({ ok: true, data: { tree: MOCK_TREE } })
    vi.mocked(api.workbench.readFile).mockResolvedValue({ ok: true, data: { content: localContent, editable: true } })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /my pack/i }))
    fireEvent.click(await screen.findByRole('button', { name: /open manifest\.yaml/i }))

    await waitFor(() => expect(screen.getByTestId('editor-mode-form')).toBeInTheDocument())

    // Default is YAML mode — raw textarea is visible
    expect(screen.getByTestId('file-editor')).toBeInTheDocument()
    expect(screen.queryByTestId('form-editor')).not.toBeInTheDocument()

    // Switch to form mode
    fireEvent.click(screen.getByTestId('editor-mode-form'))

    await waitFor(() => {
      expect(screen.getByTestId('form-editor')).toBeInTheDocument()
      expect(screen.queryByTestId('file-editor')).not.toBeInTheDocument()
    })

    // Switch back to YAML mode
    fireEvent.click(screen.getByTestId('editor-mode-yaml'))

    await waitFor(() => {
      expect(screen.getByTestId('file-editor')).toBeInTheDocument()
      expect(screen.queryByTestId('form-editor')).not.toBeInTheDocument()
    })
  })
})
