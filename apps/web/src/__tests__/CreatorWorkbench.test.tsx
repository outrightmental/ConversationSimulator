// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import CreatorWorkbench from '../screens/CreatorWorkbench'
import type { WorkbenchPack, FileNode } from '../api/client'

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

type FetchResponse = { ok: boolean; status?: number; json?: () => Promise<unknown>; text?: () => Promise<string> }

function stubFetch(handler: (url: string, opts?: RequestInit) => FetchResponse) {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, opts?: RequestInit) => Promise.resolve(handler(url, opts))),
  )
}

function okJson(data: unknown): FetchResponse {
  return { ok: true, json: () => Promise.resolve(data) }
}

function renderWorkbench() {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <CreatorWorkbench />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  // Default: list-packs returns both packs; everything else is pending
  stubFetch((url) => {
    if (url.includes('/api/workbench/packs') && !url.includes('/files') && !url.includes('/file') && !url.includes('/copy-to-local')) {
      return okJson([OFFICIAL_PACK, LOCAL_PACK])
    }
    return { ok: false, status: 404, text: () => Promise.resolve('Not found') }
  })
})

describe('CreatorWorkbench', () => {
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
    stubFetch((url) => {
      if (url.includes('/api/workbench/packs') && url.includes('/files')) {
        return okJson({ tree: MOCK_TREE })
      }
      if (url.includes('/api/workbench/packs') && !url.includes('/')) {
        return okJson([OFFICIAL_PACK, LOCAL_PACK])
      }
      return okJson([OFFICIAL_PACK, LOCAL_PACK])
    })

    renderWorkbench()
    const packBtn = await screen.findByRole('button', { name: /job interview/i })
    fireEvent.click(packBtn)

    await waitFor(() => {
      expect(screen.getByRole('tree')).toBeInTheDocument()
    })
  })

  it('shows file content when a YAML file is selected', async () => {
    stubFetch((url) => {
      if (url.includes('/files')) return okJson({ tree: MOCK_TREE })
      if (url.includes('/file?')) return okJson({ content: MANIFEST_CONTENT, editable: false })
      return okJson([OFFICIAL_PACK, LOCAL_PACK])
    })

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
    stubFetch((url) => {
      if (url.includes('/files')) return okJson({ tree: MOCK_TREE })
      if (url.includes('/file?')) return okJson({ content: MANIFEST_CONTENT, editable: false })
      return okJson([OFFICIAL_PACK, LOCAL_PACK])
    })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /job interview/i }))
    fireEvent.click(await screen.findByRole('button', { name: /open manifest\.yaml/i }))

    await waitFor(() => {
      expect(screen.getByTestId('read-only-badge')).toBeInTheDocument()
    })
  })

  it('shows create-local-copy button for read-only files', async () => {
    stubFetch((url) => {
      if (url.includes('/files')) return okJson({ tree: MOCK_TREE })
      if (url.includes('/file?')) return okJson({ content: MANIFEST_CONTENT, editable: false })
      return okJson([OFFICIAL_PACK, LOCAL_PACK])
    })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /job interview/i }))
    fireEvent.click(await screen.findByRole('button', { name: /open manifest\.yaml/i }))

    await waitFor(() => {
      expect(screen.getByTestId('copy-to-local-button')).toBeInTheDocument()
    })
  })

  it('shows no save button for read-only official pack', async () => {
    stubFetch((url) => {
      if (url.includes('/files')) return okJson({ tree: MOCK_TREE })
      if (url.includes('/file?')) return okJson({ content: MANIFEST_CONTENT, editable: false })
      return okJson([OFFICIAL_PACK, LOCAL_PACK])
    })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /job interview/i }))
    fireEvent.click(await screen.findByRole('button', { name: /open manifest\.yaml/i }))

    await waitFor(() => {
      expect(screen.queryByTestId('save-button')).not.toBeInTheDocument()
    })
  })

  it('shows editable textarea and save button for local-dev pack', async () => {
    const localContent = 'name: My Pack\n'
    stubFetch((url) => {
      if (url.includes('/files')) return okJson({ tree: MOCK_TREE })
      if (url.includes('/file?')) return okJson({ content: localContent, editable: true })
      return okJson([OFFICIAL_PACK, LOCAL_PACK])
    })

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
    stubFetch((url) => {
      if (url.includes('/files')) return okJson({ tree: MOCK_TREE })
      if (url.includes('/file?')) return okJson({ content: localContent, editable: true })
      return okJson([OFFICIAL_PACK, LOCAL_PACK])
    })

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
    const putSpy = vi.fn().mockResolvedValue({ ok: true })
    stubFetch((url, opts) => {
      if (url.includes('/files')) return okJson({ tree: MOCK_TREE })
      if (url.includes('/file?') && (!opts || opts.method !== 'PUT')) {
        return okJson({ content: localContent, editable: true })
      }
      if (url.includes('/file?') && opts?.method === 'PUT') {
        putSpy()
        return okJson({ ok: true })
      }
      return okJson([OFFICIAL_PACK, LOCAL_PACK])
    })

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
    expect(putSpy).toHaveBeenCalledOnce()
  })

  it('shows unsupported label for non-text files in tree', async () => {
    stubFetch((url) => {
      if (url.includes('/files')) return okJson({ tree: MOCK_TREE })
      return okJson([OFFICIAL_PACK, LOCAL_PACK])
    })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /job interview/i }))

    await waitFor(() => {
      expect(screen.getByText('unsupported')).toBeInTheDocument()
    })
  })

  it('shows pack error when API fails', async () => {
    stubFetch(() => ({ ok: false, status: 500, text: () => Promise.resolve('Server error') }))

    renderWorkbench()

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
  })

  it('copy-to-local button triggers copy and switches to new pack', async () => {
    const newPack: WorkbenchPack = { kind: 'local-dev', slug: 'job-interview-copy', pack_id: 'local.job_interview_copy', name: 'Job Interview', editable: true }
    const copySpy = vi.fn().mockReturnValue(okJson(newPack))

    stubFetch((url) => {
      if (url.includes('/copy-to-local')) return copySpy()
      if (url.includes('/files')) return okJson({ tree: MOCK_TREE })
      if (url.includes('/file?')) return okJson({ content: MANIFEST_CONTENT, editable: false })
      return okJson([OFFICIAL_PACK, LOCAL_PACK])
    })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /job interview/i }))
    fireEvent.click(await screen.findByRole('button', { name: /open manifest\.yaml/i }))

    const copyBtn = await screen.findByTestId('copy-to-local-button')
    fireEvent.click(copyBtn)

    await waitFor(() => {
      expect(copySpy).toHaveBeenCalledOnce()
    })

    // After copy, the file editor should be cleared (no file selected)
    await waitFor(() => {
      expect(screen.queryByTestId('file-editor')).not.toBeInTheDocument()
    })
  })

  it('shows a valid badge when the pack validates cleanly', async () => {
    stubFetch((url) => {
      if (url.includes('/validate')) return okJson({ valid: true, errors: [], warnings: [] })
      if (url.includes('/files')) return okJson({ tree: MOCK_TREE })
      return okJson([OFFICIAL_PACK, LOCAL_PACK])
    })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /my pack/i }))

    await waitFor(() => {
      expect(screen.getByTestId('validation-panel')).toHaveTextContent(/valid/i)
    })
  })

  it('lists validation errors when the pack is invalid', async () => {
    stubFetch((url) => {
      if (url.includes('/validate')) {
        return okJson({
          valid: false,
          errors: [
            { severity: 'error', rule_id: 'SCHEMA_VIOLATION', file: 'manifest.yaml', pointer: '/author', message: "'author' is a required property", suggested_fix: 'Add author' },
          ],
          warnings: [],
        })
      }
      if (url.includes('/files')) return okJson({ tree: MOCK_TREE })
      return okJson([OFFICIAL_PACK, LOCAL_PACK])
    })

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
    stubFetch((url, opts) => {
      if (url.includes('/file?') && opts?.method === 'PUT') {
        return okJson({
          valid: false,
          ok: true,
          validation: {
            valid: false,
            errors: [
              { severity: 'error', rule_id: 'INVALID_MANIFEST_YAML', file: 'manifest.yaml', pointer: '', message: 'manifest.yaml must be a YAML mapping', suggested_fix: 'Fix YAML' },
            ],
            warnings: [],
          },
        })
      }
      if (url.includes('/file?')) return okJson({ content: localContent, editable: true })
      if (url.includes('/validate')) return okJson({ valid: true, errors: [], warnings: [] })
      if (url.includes('/files')) return okJson({ tree: MOCK_TREE })
      return okJson([OFFICIAL_PACK, LOCAL_PACK])
    })

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
    stubFetch((url, opts) => {
      // Save returns a clean validation once the validator has recovered.
      if (url.includes('/file?') && opts?.method === 'PUT') {
        return okJson({ ok: true, validation: { valid: true, errors: [], warnings: [] } })
      }
      if (url.includes('/file?')) return okJson({ content: localContent, editable: true })
      // Initial on-select validation fails: the validator is down.
      if (url.includes('/validate')) return { ok: false, status: 500, text: () => Promise.resolve('boom') }
      if (url.includes('/files')) return okJson({ tree: MOCK_TREE })
      return okJson([OFFICIAL_PACK, LOCAL_PACK])
    })

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
    stubFetch((url) => {
      if (url.includes('/validate')) {
        return okJson({
          valid: false,
          errors: [
            { severity: 'error', rule_id: 'SCHEMA_VIOLATION', file: 'manifest.yaml', pointer: '/author', message: 'author is required', suggested_fix: 'Add author field' },
            { severity: 'error', rule_id: 'SCHEMA_VIOLATION', file: 'scenarios/basic.yaml', pointer: '/summary', message: 'summary is required', suggested_fix: 'Add summary' },
          ],
          warnings: [],
        })
      }
      if (url.includes('/files')) return okJson({ tree: MOCK_TREE })
      return okJson([OFFICIAL_PACK, LOCAL_PACK])
    })

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
    stubFetch((url) => {
      if (url.includes('/validate')) {
        return okJson({
          valid: false,
          errors: [
            { severity: 'error', rule_id: 'SCHEMA_VIOLATION', file: 'manifest.yaml', pointer: '/author', message: 'author is required', suggested_fix: 'Add author' },
          ],
          warnings: [],
        })
      }
      if (url.includes('/files')) return okJson({ tree: MOCK_TREE })
      if (url.includes('/file?')) return okJson({ content: 'pack_id: x\n', editable: true })
      return okJson([OFFICIAL_PACK, LOCAL_PACK])
    })

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
    stubFetch((url) => {
      if (url.includes('/validate')) {
        return okJson({
          valid: false,
          errors: [
            { severity: 'error', rule_id: 'FORBIDDEN_FILE', file: 'run.sh', pointer: '', message: "Executable file not allowed: 'run.sh'", suggested_fix: 'Remove this file', category: 'security' },
          ],
          warnings: [],
        })
      }
      if (url.includes('/files')) return okJson({ tree: MOCK_TREE })
      return okJson([OFFICIAL_PACK, LOCAL_PACK])
    })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /my pack/i }))

    await waitFor(() => {
      const panel = screen.getByTestId('validation-panel')
      expect(panel).toHaveTextContent('SECURITY')
      expect(screen.getByTestId('security-badge')).toBeInTheDocument()
    })
  })

  it('shows suggested fix text for each finding', async () => {
    stubFetch((url) => {
      if (url.includes('/validate')) {
        return okJson({
          valid: false,
          errors: [
            { severity: 'error', rule_id: 'SCHEMA_VIOLATION', file: 'manifest.yaml', pointer: '/author', message: 'author required', suggested_fix: 'Add the author field to manifest.yaml' },
          ],
          warnings: [],
        })
      }
      if (url.includes('/files')) return okJson({ tree: MOCK_TREE })
      return okJson([OFFICIAL_PACK, LOCAL_PACK])
    })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /my pack/i }))

    await waitFor(() => {
      expect(screen.getByTestId('validation-panel')).toHaveTextContent('Add the author field to manifest.yaml')
    })
  })

  it('shows links to authoring docs alongside findings', async () => {
    stubFetch((url) => {
      if (url.includes('/validate')) {
        return okJson({
          valid: false,
          errors: [
            { severity: 'error', rule_id: 'SCHEMA_VIOLATION', file: 'manifest.yaml', pointer: '/author', message: 'author required', suggested_fix: 'See the authoring guide' },
          ],
          warnings: [],
        })
      }
      if (url.includes('/files')) return okJson({ tree: MOCK_TREE })
      return okJson([OFFICIAL_PACK, LOCAL_PACK])
    })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /my pack/i }))

    const guideLink = await screen.findByRole('link', { name: /authoring guide/i })
    expect(guideLink).toHaveAttribute('href', expect.stringContaining('scenario-authoring'))
    expect(screen.getByRole('link', { name: /validation rules/i })).toBeInTheDocument()
  })

  it('shows copy validation button', async () => {
    stubFetch((url) => {
      if (url.includes('/validate')) {
        return okJson({
          valid: false,
          errors: [
            { severity: 'error', rule_id: 'SCHEMA_VIOLATION', file: 'manifest.yaml', pointer: '/author', message: 'author required', suggested_fix: 'Fix it' },
          ],
          warnings: [],
        })
      }
      if (url.includes('/files')) return okJson({ tree: MOCK_TREE })
      return okJson([OFFICIAL_PACK, LOCAL_PACK])
    })

    renderWorkbench()
    fireEvent.click(await screen.findByRole('button', { name: /my pack/i }))

    await waitFor(() => {
      expect(screen.getByTestId('copy-validation-button')).toBeInTheDocument()
    })
  })

  it('shows service error when validator API fails', async () => {
    stubFetch((url) => {
      if (url.includes('/validate')) return { ok: false, status: 500, text: () => Promise.resolve('Internal server error') }
      if (url.includes('/files')) return okJson({ tree: MOCK_TREE })
      return okJson([OFFICIAL_PACK, LOCAL_PACK])
    })

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

    stubFetch((url) => {
      if (url.includes('/files')) return okJson({ tree: MOCK_TREE })
      if (url.includes('/file?')) return okJson({ content: localContent, editable: true })
      return okJson([OFFICIAL_PACK, LOCAL_PACK])
    })

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

    vi.unstubAllGlobals()
  })
})
