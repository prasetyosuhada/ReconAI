import { render, screen, within } from '@testing-library/react'
import { expect, test } from 'vitest'
import { ExtractionReviewContext } from '../src/components/review/ExtractionReviewContext'

test('shows partial scanned-page coverage and persisted diagnostics', () => {
  render(
    <ExtractionReviewContext
      loading={false}
      metadata={{
        extraction_method: 'pdf_vision',
        source_page_count: 11,
        processed_page_count: 10,
        page_limit_applied: true,
        text_page_numbers: [],
        vision_page_numbers: [1, 2],
        rendered_page_numbers: [1, 2],
        warnings: ['Source is blurred'],
        low_confidence_fields: ['vendor_name'],
        risk_flags: ['partial_document_page_limit'],
      }}
    />
  )
  const context = within(screen.getByRole('region', { name: 'Extraction context' }))
  expect(context.getByText('PDF page vision')).toBeInTheDocument()
  expect(context.getByText('Only 10 of 11 source pages were processed.')).toBeInTheDocument()
  expect(context.getByText('Source Is Blurred')).toBeInTheDocument()
  expect(context.getByText('Vendor Name')).toBeInTheDocument()
  expect(context.getByText('Partial Document Page Limit')).toBeInTheDocument()
  expect(context.getAllByText('1, 2')).toHaveLength(2)
})

test('distinguishes absent diagnostics from empty recorded diagnostics', () => {
  const view = render(<ExtractionReviewContext loading={false} metadata={null} />)
  expect(screen.getByText(/diagnostics are not available/)).toBeInTheDocument()
  view.rerender(
    <ExtractionReviewContext
      loading={false}
      metadata={{ warnings: [], risk_flags: [], low_confidence_fields: [] }}
    />
  )
  expect(screen.getByText('No warnings recorded.')).toBeInTheDocument()
  expect(screen.getByText('No risk flags recorded.')).toBeInTheDocument()
  expect(screen.getAllByText('Not recorded').length).toBeGreaterThan(0)
})

test('uses review risk flags when extraction metadata does not contain them', () => {
  render(
    <ExtractionReviewContext
      loading={false}
      metadata={{}}
      fallbackRiskFlags={['partial_document_render_failure']}
    />
  )
  expect(screen.getByText('Partial Document Render Failure')).toBeInTheDocument()
  expect(screen.getByText('Only part of this source document was processed.')).toBeInTheDocument()
})
