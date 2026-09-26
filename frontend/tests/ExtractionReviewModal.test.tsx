import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, test, vi } from 'vitest'
import { ExtractionReviewModal } from '../src/components/review/ExtractionReviewModal'
import type { ReviewItemResponse } from '../src/services/api'

const item: ReviewItemResponse = {
  id: 'review-1',
  review_type: 'extraction',
  source_type: 'document',
  source_id: 'doc-1',
  status: 'pending',
  priority: 'normal',
  title: 'Review Needed: scanned.pdf',
  summary: 'Uncertain extraction',
  original_payload: { document_type: 'invoice', vendor_name: 'Original supplier' },
  created_at: '2026-09-26',
  updated_at: '2026-09-26',
}
const extraction = {
  id: 'extraction-1',
  document_id: 'doc-1',
  vendor_name: 'Persisted supplier',
  transaction_date: '2026-09-01',
  currency: 'IDR',
  subtotal_amount: 100,
  tax_amount: 10,
  total_amount: 110,
  line_items: [],
  confidence_score: 0.4,
  status: 'draft',
  provider_metadata: {
    extraction_method: 'pdf_vision',
    source_page_count: 2,
    processed_page_count: 2,
    warnings: ['Blurred source'],
  },
}
const post = vi.fn()
const onClose = vi.fn()
const onResolved = vi.fn()
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
const invalid = () =>
  json(
    {
      error: {
        code: 'extraction_validation_failed',
        message: 'The extraction still contains fields that must be corrected.',
        details: [
          { field: 'vendor_name', code: 'missing_vendor_name', message: 'Vendor is required.' },
        ],
      },
    },
    422
  )

beforeEach(() => {
  post.mockReset()
  onClose.mockReset()
  onResolved.mockReset()
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, options?: RequestInit) => {
      if (options?.method === 'POST') return post(url, JSON.parse(String(options.body)))
      if (url.includes('/chart-of-accounts')) return Promise.resolve(json({ items: [] }))
      if (url.includes('/extractions/latest')) return Promise.resolve(json(extraction))
      if (url.endsWith('/content'))
        return Promise.resolve(json({ error: { code: 'source_content_unavailable' } }, 410))
      throw new Error(`Unexpected request: ${url}`)
    })
  )
})

async function openReview() {
  render(<ExtractionReviewModal item={item} onClose={onClose} onResolved={onResolved} />)
  await screen.findByText('Persisted supplier')
  await screen.findByText(/The original file is unavailable/)
  return userEvent.setup()
}

test('valid approve-as-is resolves only after the API succeeds, even with missing source bytes', async () => {
  let finish!: (value: Response) => void
  post.mockReturnValue(
    new Promise<Response>((resolve) => {
      finish = resolve
    })
  )
  const user = await openReview()
  const button = screen.getByRole('button', { name: 'Confirm Extraction' })
  await user.click(button)
  expect(button).toBeDisabled()
  fireEvent.click(button)
  expect(post).toHaveBeenCalledTimes(1)
  expect(post.mock.calls[0][0]).toBe('/api/v1/review-items/review-1/approve')
  expect(onResolved).not.toHaveBeenCalled()
  expect(onClose).not.toHaveBeenCalled()
  await act(async () =>
    finish(json({ status: 'approved', next_workflow_status: 'bookkeeping_review_required' }))
  )
  await waitFor(() => expect(onResolved).toHaveBeenCalledTimes(1))
  expect(onClose).toHaveBeenCalledTimes(1)
})

test('invalid approve-as-is opens the editor with accessible field errors and keeps the review open', async () => {
  post.mockResolvedValue(invalid())
  const user = await openReview()
  await user.click(screen.getByRole('button', { name: 'Confirm Extraction' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Vendor is required.')
  const vendor = screen.getByPlaceholderText('Vendor name')
  expect(vendor).toHaveAttribute('aria-invalid', 'true')
  expect(vendor).toHaveAccessibleDescription('Vendor is required.')
  expect(screen.getByRole('button', { name: 'Save Fields & Continue' })).toBeEnabled()
  expect(onClose).not.toHaveBeenCalled()
  expect(onResolved).not.toHaveBeenCalled()
})

test('invalid correction retains draft and a corrected retry submits only editable accounting fields', async () => {
  post.mockResolvedValueOnce(invalid()).mockResolvedValueOnce(json({ status: 'edited' }))
  const user = await openReview()
  await user.click(screen.getAllByRole('button', { name: 'Edit Fields' })[0])
  const vendor = screen.getByPlaceholderText('Vendor name')
  await user.clear(vendor)
  await user.type(vendor, '   ')
  await user.click(screen.getByRole('button', { name: 'Save Fields & Continue' }))
  await screen.findByRole('alert')
  expect(vendor).toHaveValue('   ')
  expect(onResolved).not.toHaveBeenCalled()
  await user.clear(vendor)
  await user.type(vendor, 'Corrected supplier')
  await user.click(screen.getByRole('button', { name: 'Save Fields & Continue' }))
  await waitFor(() => expect(onResolved).toHaveBeenCalledTimes(1))
  expect(post.mock.calls[1][0]).toBe('/api/v1/review-items/review-1/edit')
  expect(post.mock.calls[1][1].edited_payload).toEqual({
    document_type: 'invoice',
    vendor_name: 'Corrected supplier',
    transaction_date: '2026-09-01',
    currency: 'IDR',
    subtotal_amount: 100,
    tax_amount: 10,
    total_amount: 110,
    line_items: [],
  })
  expect(onClose).toHaveBeenCalledTimes(1)
})

test.each([
  [409, 'review_already_resolved', 'This review has already been resolved. Refresh the queue.'],
  [
    503,
    'review_continuation_failed',
    'Bookkeeping could not complete. Your review is still pending; please retry.',
  ],
])(
  'shows HTTP %s without losing the correction or claiming success',
  async (status, code, message) => {
    post.mockResolvedValue(json({ error: { code, message } }, status))
    const user = await openReview()
    await user.click(screen.getAllByRole('button', { name: 'Edit Fields' })[0])
    const vendor = screen.getByPlaceholderText('Vendor name')
    await user.clear(vendor)
    await user.type(vendor, 'Unsaved correction')
    await user.click(screen.getByRole('button', { name: 'Save Fields & Continue' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(message)
    expect(vendor).toHaveValue('Unsaved correction')
    expect(onClose).not.toHaveBeenCalled()
    expect(onResolved).not.toHaveBeenCalled()
  }
)

test('reject submits the reason and surfaces a concurrent conflict', async () => {
  post.mockResolvedValue(
    json({ error: { code: 'review_already_resolved', message: 'Refresh the queue.' } }, 409)
  )
  const user = await openReview()
  await user.click(screen.getByRole('button', { name: 'Reject Item' }))
  await user.type(
    screen.getByPlaceholderText('e.g. Blurry scan, illegible amounts...'),
    'Unreadable source'
  )
  await user.click(screen.getByRole('button', { name: 'Reject' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Refresh the queue.')
  expect(post).toHaveBeenCalledWith('/api/v1/review-items/review-1/reject', {
    rejection_reason: 'Unreadable source',
  })
  expect(onResolved).not.toHaveBeenCalled()
})

test('positive total leaves payment status unknown', async () => {
  await openReview()
  expect(screen.getAllByText('Unknown').length).toBeGreaterThan(0)
  expect(screen.queryByText('Paid', { exact: true })).not.toBeInTheDocument()
})
