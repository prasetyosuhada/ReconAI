import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, test, vi } from 'vitest'
import { SourceDocumentViewer } from '../src/components/review/SourceDocumentViewer'

const fetchMock = vi.fn()
const revoke = vi.fn()
beforeEach(() => {
  fetchMock.mockReset()
  revoke.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test-source')
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(revoke)
})

function source(mime = 'application/pdf') {
  fetchMock.mockImplementation(
    async () => new Response(new Blob(['source bytes']), { headers: { 'content-type': mime } })
  )
}
function viewer(pageCount: number | null = 2) {
  return render(
    <SourceDocumentViewer documentId="doc-1" filename="scanned.pdf" pageCount={pageCount} />
  )
}

test('loads source and bounds multi-page navigation, with the same controlled Open Source URL', async () => {
  source()
  const user = userEvent.setup()
  viewer()
  expect(screen.getByText('Loading source document…')).toBeInTheDocument()
  expect(await screen.findByTitle('scanned.pdf, page 1')).toHaveAttribute(
    'src',
    'blob:test-source#page=1'
  )
  expect(screen.getByRole('link', { name: 'Open Source' })).toHaveAttribute(
    'href',
    '/api/v1/documents/doc-1/content'
  )
  expect(screen.getByRole('button', { name: 'Show previous PDF page' })).toBeDisabled()
  await user.click(screen.getByRole('button', { name: 'Show next PDF page' }))
  expect(screen.getByTitle('scanned.pdf, page 2')).toHaveAttribute('src', 'blob:test-source#page=2')
  expect(screen.getByText('Page 2 of 2')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Show next PDF page' })).toBeDisabled()
  await user.click(screen.getByRole('button', { name: 'Show previous PDF page' }))
  expect(screen.getByText('Page 1 of 2')).toBeInTheDocument()
})

test('single-page PDF cannot advance to fictitious pages', async () => {
  source()
  viewer(1)
  await screen.findByTitle('scanned.pdf, page 1')
  const next = screen.getByRole('button', { name: 'Show next PDF page' })
  expect(next).toBeDisabled()
  fireEvent.click(next)
  expect(screen.getByText('Page 1 of 1')).toBeInTheDocument()
})

test('unknown page count uses browser controls without unbounded custom navigation', async () => {
  source()
  viewer(null)
  await screen.findByTitle('scanned.pdf, page 1')
  expect(screen.queryByRole('button', { name: 'Show next PDF page' })).not.toBeInTheDocument()
  expect(screen.getByText(/Use the PDF viewer controls/)).toBeInTheDocument()
})

test.each(['image/jpeg', 'image/png', 'image/webp'])(
  'renders %s as a contained image',
  async (mime) => {
    source(mime)
    viewer(null)
    const image = await screen.findByRole('img', { name: 'Source document: scanned.pdf' })
    expect(image).toHaveAttribute('src', 'blob:test-source')
    expect(image).toHaveClass('object-contain')
    expect(screen.queryByRole('button', { name: 'Show next PDF page' })).not.toBeInTheDocument()
  }
)

test.each([
  [410, 'source_content_unavailable', /The original file is unavailable/],
  [415, 'unsupported_source_media_type', /not supported for inline review/],
  [404, 'document_not_found', /could not be loaded/],
])('shows explicit source failure for HTTP %s', async (status, code, message) => {
  fetchMock.mockResolvedValue(new Response(JSON.stringify({ error: { code } }), { status }))
  viewer()
  expect(await screen.findByText(message)).toBeInTheDocument()
  expect(document.querySelector('iframe, img')).toBeNull()
})

test('does not render an unsupported success MIME', async () => {
  source('text/html')
  viewer()
  expect(await screen.findByText(/not supported for inline review/)).toBeInTheDocument()
  expect(document.querySelector('iframe, img')).toBeNull()
})

test('shows a fallback after an image rendering error', async () => {
  source('image/png')
  viewer()
  const element = await screen.findByRole('img')
  fireEvent.error(element)
  expect(screen.getByText(/could not render this source file inline/)).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Open Source' })).toBeInTheDocument()
})

test('missing document ID does not fetch or invent source evidence', () => {
  render(<SourceDocumentViewer documentId={null} filename="Unknown" pageCount={null} />)
  expect(screen.getByText(/No source document is linked/)).toBeInTheDocument()
  expect(fetchMock).not.toHaveBeenCalled()
  expect(screen.queryByRole('link')).not.toBeInTheDocument()
})

test('revokes object URLs and resets page when switching source documents', async () => {
  source()
  const user = userEvent.setup()
  const view = viewer()
  await screen.findByTitle('scanned.pdf, page 1')
  await user.click(screen.getByRole('button', { name: 'Show next PDF page' }))
  view.rerender(<SourceDocumentViewer documentId="doc-2" filename="second.pdf" pageCount={1} />)
  await screen.findByTitle('second.pdf, page 1')
  expect(revoke).toHaveBeenCalledWith('blob:test-source')
  view.unmount()
  await waitFor(() => expect(revoke).toHaveBeenCalledTimes(2))
})

test('PDF navigation is operable with the keyboard', async () => {
  source()
  const user = userEvent.setup()
  viewer()
  await screen.findByTitle('scanned.pdf, page 1')
  screen.getByRole('button', { name: 'Show next PDF page' }).focus()
  await user.keyboard('{Enter}')
  expect(screen.getByText('Page 2 of 2')).toBeInTheDocument()
})
