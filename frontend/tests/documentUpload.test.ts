import assert from 'node:assert/strict'
import { test } from 'vitest'
import { validateDocumentUpload } from '../src/utils/documentUpload.ts'

for (const [name, type] of [
  ['invoice.pdf', 'application/pdf'],
  ['receipt.png', 'image/png'],
  ['receipt.jpg', 'image/jpeg'],
  ['receipt.jpeg', 'image/jpg'],
  ['receipt.webp', 'image/webp'],
]) {
  test(`accepts ${type} at the API's exact 10 MB limit`, () => {
    assert.equal(validateDocumentUpload({ name, type, size: 10 * 1024 * 1024 }), null)
  })
}

test('rejects one byte over the API limit', () => {
  assert.equal(
    validateDocumentUpload({
      name: 'invoice.pdf',
      type: 'application/pdf',
      size: 10 * 1024 * 1024 + 1,
    }),
    'File size exceeds maximum limit of 10 MB.'
  )
})

test('rejects empty supported files', () => {
  assert.equal(
    validateDocumentUpload({ name: 'receipt.webp', type: 'image/webp', size: 0 }),
    'The selected file is empty.'
  )
})

test('accepts extension fallback when browser MIME is unavailable', () => {
  assert.equal(validateDocumentUpload({ name: 'receipt.WEBP', type: '', size: 100 }), null)
})

test('rejects unsupported files and misleading extensions', () => {
  for (const name of ['notes.txt', 'receipt.webp.exe']) {
    assert.equal(
      validateDocumentUpload({ name, type: 'text/plain', size: 100 }),
      'Only PDF, PNG, JPEG, and WebP files are supported.'
    )
  }
})
