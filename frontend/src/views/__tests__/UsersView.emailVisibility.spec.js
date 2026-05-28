import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const root = resolve(__dirname, '../../..')

describe('UsersView admin email visibility', () => {
  it('adds a safe admin-only email summary viewer without auto-check controls', () => {
    const usersView = readFileSync(resolve(root, 'src/views/admin/UsersView.vue'), 'utf8')

    expect(usersView).toContain('邮箱数量')
    expect(usersView).toContain('查看邮箱')
    expect(usersView).toContain('用户邮箱列表')
    expect(usersView).toContain('selectedUserEmails')

    expect(usersView).not.toContain('checkEmail(')
    expect(usersView).not.toContain('checkEmails(')
    expect(usersView).not.toContain('开始收码')
  })
})
