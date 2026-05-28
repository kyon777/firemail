import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const root = resolve(__dirname, '../../..')

describe('navigation cleanup', () => {
  it('removes unused public pages from the visible navigation and routes', () => {
    const appVue = readFileSync(resolve(root, 'src/App.vue'), 'utf8')
    const router = readFileSync(resolve(root, 'src/router/index.js'), 'utf8')

    expect(appVue).not.toContain('邮件搜索')
    expect(appVue).not.toContain('index="/search"')
    expect(appVue).not.toContain('关于')
    expect(appVue).not.toContain('index="/about"')
    expect(router).not.toContain("path: '/search'")
    expect(router).not.toContain('SearchView.vue')
    expect(router).not.toContain("path: '/about'")
    expect(router).not.toContain('AboutView.vue')
  })
})
