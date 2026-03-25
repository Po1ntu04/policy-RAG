import { chatAPI } from '../../services/api'

export default {
  namespaced: true,
  state: {
    // 表格列表
    tables: [],
    // 当前表格
    currentTable: null,
    // 生成状态
    generationStatus: 'idle', // idle, generating, completed, failed
    // 表格配置
    tableConfig: {
      maxRows: 100,
      columns: [],
      query: '',
      description: '',
      includeReasoning: false
    }
  },
  mutations: {
    // 设置表格列表
    SET_TABLES(state, tables) {
      state.tables = tables
    },
    // 添加表格
    ADD_TABLE(state, table) {
      state.tables.unshift(table)
    },
    // 设置当前表格
    SET_CURRENT_TABLE(state, table) {
      state.currentTable = table
    },
    // 更新表格
    UPDATE_TABLE(state, { tableId, updates }) {
      const index = state.tables.findIndex(t => t.id === tableId)
      if (index !== -1) {
        state.tables[index] = { ...state.tables[index], ...updates }
      }
      if (state.currentTable && state.currentTable.id === tableId) {
        state.currentTable = { ...state.currentTable, ...updates }
      }
    },
    // 删除表格
    REMOVE_TABLE(state, tableId) {
      state.tables = state.tables.filter(t => t.id !== tableId)
      if (state.currentTable && state.currentTable.id === tableId) {
        state.currentTable = null
      }
    },
    // 设置生成状态
    SET_GENERATION_STATUS(state, status) {
      state.generationStatus = status
    },
    // 设置表格配置
    SET_TABLE_CONFIG(state, config) {
      state.tableConfig = { ...state.tableConfig, ...config }
    },
    // 重置表格配置
    RESET_TABLE_CONFIG(state) {
      state.tableConfig = {
        maxRows: 100,
        columns: [],
        query: '',
        description: '',
        includeReasoning: false
      }
    }
  },
  actions: {
    // 生成表格
    async generateTable({ commit }, config) {
      try {
        commit('SET_GENERATION_STATUS', 'generating')
        commit('SET_TABLE_CONFIG', config)

        // 使用聊天接口生成结构化表格（JSON 输出）
        const escapeBraces = (s) => s?.replace(/\{/g, '{{').replace(/\}/g, '}}') || ''

        // 指标表（V1）标准列与字段释义（来源：docs/milestones_M0_to_V2.md）
        const indicatorHeaders = [
          '年度',
          '一级指标',
          '二级指标',
          '评分细则',
          '分值',
          '目标来源',
          '完成时限',
          '是否完成',
          '责任单位',
          '责任处室'
        ]
        const indicatorFieldGuide = [
          '字段释义（用于“指标表/绩效考核表”）：',
          '- 年度：指标所属年份（整数，如 2023）',
          '- 一级指标：顶层分类（只包含“一、核心工作”和“二、重点工作”，按重要度分即可）',
          '- 二级指标：总结归纳一个具体事项/任务名称（如“1.突破重大技术”）',
          '- 评分细则：评分规则的原文/要点（可分点；过长请截断）',
          '- 分值：该二级指标对应的总分（数值；两位小数；缺失则空）',
          '- 目标来源：指标来源文件或依据条目（含文件名、页码、条款号等；过长请截断）',
          '- 完成时限：截止日期（YYYY-MM-DD；仅有年份则用年末，例 2023-12-31）',
          '- 是否完成：枚举：已完成/未完成/进行中（无法判断则留空）',
          '- 责任单位：对二级指标的主责单位（如“区体育局”）',
          '- 责任处室：具体承办处室，多个用逗号分隔（过长请保留 1-3 个）'
        ].join('\n')

        const queryText = String(config?.query || '')
        const descText = String(config?.description || '')
        const wantsIndicatorSchema = /指标|绩效|考核|评分细则|分值|责任单位|责任处室/.test(queryText + ' ' + descText)

        const systemPromptRaw = [
          '你是一个结构化数据抽取助手。',
          '根据用户的查询与列名，从可用的政务文档内容中抽取表格数据。',
          '严格只返回 JSON，不要包含任何多余文本或解释，不要使用 Markdown 或 ```json 代码块。',
          '为避免输出过长导致 JSON 被截断：每个单元格尽量简短（优先截断字段内容，保证 JSON 完整闭合）。',
          '如果用户在生成“绩效考核指标表/指标表”，请优先使用标准列，并遵循字段释义。',
          indicatorFieldGuide,
          '重要：如果用户提供了“列名”列表，则：',
          '- JSON 中 headers 必须与该列名列表完全一致（顺序一致、名称一致），不得自行增删或改名。',
          '- rows 中每个对象必须包含 headers 的全部键；缺失值用空字符串。',
          'JSON 模式如下：',
          '{',
          '  "title": string,',
          '  "description": string | null,',
          '  "headers": string[],',
          '  "rows": Array<Record<string, string>>,',
          '  "generationStats": {',
          '    "sourceDocuments": number,',
          '    "averageConfidence": number',
          '  }',
          '}',
          'rows 的每一项为对象，键名与 headers 完全一致；缺失的数据用空字符串。',
          '当用户要求显示推理过程时，请在每个 row 对象中额外包含 "__reasoning" 字段（不出现在 headers 中），用 50-100 字简述该行数据的来源与提取依据。',
          '中文输出。'
        ].join('\n')
        const systemPrompt = escapeBraces(systemPromptRaw)

        const normalizedCols = Array.isArray(config.columns)
          ? config.columns.map(c => String(c || '').trim()).filter(Boolean)
          : []
        const hasColumns = normalizedCols.length > 0

        // TableGeneration.vue 里有一组默认占位列（项目名称/负责部门/完成时间/备注）。
        // 如果用户其实想要“指标表标准列”，但未手动清空占位列，则这里把它视为“未指定列”。
        const placeholderCols = ['项目名称', '负责部门', '完成时间', '备注']
        const isPlaceholderColumns = normalizedCols.length === placeholderCols.length
          && normalizedCols.every((c, i) => c === placeholderCols[i])

        const useExplicitColumns = hasColumns && !(wantsIndicatorSchema && isPlaceholderColumns)
        const columnsText = useExplicitColumns
          ? `列名: ${normalizedCols.join(', ')}`
          : (wantsIndicatorSchema
            ? `列名: ${indicatorHeaders.join(', ')}`
            : '列名: （请根据文档内容自动识别最有信息量且易读的列名，建议 4-8 列，列名简洁明确，不要使用编号）')

        const userPromptRaw = [
          `查询: ${config.query || '自动汇总文档中的政务项目/事项表'}`,
          columnsText,
          `最大行数: ${config.maxRows || 100}`,
          config.description ? `表格说明: ${config.description}` : '',
          config.includeReasoning ? '请在每一行添加 "__reasoning" 字段，简要说明该行数据的提取依据。' : ''
        ].filter(Boolean).join('\n')
        const userPrompt = escapeBraces(userPromptRaw)

        const messagesPayload = [
          { role: 'system', content: systemPrompt },
          { role: 'user', content: userPrompt }
        ]

        // 确保 messages 格式正确传递（不依赖 chatAPI.completions 的特殊参数合并逻辑）
        const resp = await chatAPI.completions(messagesPayload, {
          useContext: true,
          contextFilter: config.contextFilter,
          includeSources: false,
          stream: false
        })

        const raw = resp?.choices?.[0]?.message?.content || ''
        // 去掉可能的 ```json 代码块包裹
        let cleaned = raw.replace(/```json|```/gim, '').trim()
        // 控制台辅助排查
        try { /* debug */ console.debug('[table] LLM raw:', cleaned.slice(0, 2000)) } catch (err) { /* ignore */ }

        const tryParse = (text) => {
          try { return JSON.parse(text) } catch { return null }
        }

        // 1) 直接解析
        let parsed = tryParse(cleaned)

        if (!parsed) {
          // 2) 提取最外层花括号包裹的 JSON 片段
          const first = cleaned.indexOf('{')
          const last = cleaned.lastIndexOf('}')
          if (first !== -1 && last !== -1 && last > first) {
            cleaned = cleaned.slice(first, last + 1)
            parsed = tryParse(cleaned)
          }
        }

        if (!parsed) {
          // 3) 移除尾随逗号，如 { ... ,}\n或[... ,]\n
          const noTrailingCommas = cleaned.replace(/,\s*([}\]])/g, '$1')
          parsed = tryParse(noTrailingCommas)
          if (!parsed) cleaned = noTrailingCommas
        }

        if (!parsed) {
          // 4) 将单引号键/值转换为双引号（尽量温和，不处理包含引号的复杂文本）
          const keysFixed = cleaned.replace(/'([^'\\]*?)'\s*:/g, '"$1":')
          const valuesFixed = keysFixed.replace(/:\s*'([^'\\]*?)'/g, ': "$1"')
          parsed = tryParse(valuesFixed)
          if (!parsed) cleaned = valuesFixed
        }

        if (!parsed) {
          // 5) 最后尝试去除不可见字符
          // eslint-disable-next-line no-control-regex
          const sanitized = cleaned.replace(/[\u0000-\u001F\u007F]/g, '')
          parsed = tryParse(sanitized)
          cleaned = sanitized
        }

        if (!parsed) {
          // 6) 试图补全可能截断的 JSON（按括号配对补齐）
          const balanceFix = (text) => {
            const openCurly = (text.match(/\{/g) || []).length
            const closeCurly = (text.match(/\}/g) || []).length
            const openSquare = (text.match(/\[/g) || []).length
            const closeSquare = (text.match(/\]/g) || []).length
            let fixed = text
            if (closeSquare < openSquare) fixed = fixed + ']'.repeat(openSquare - closeSquare)
            if (closeCurly < openCurly) fixed = fixed + '}'.repeat(openCurly - closeCurly)
            return fixed
          }
          const balanced = balanceFix(cleaned)
          parsed = tryParse(balanced)
          if (!parsed) cleaned = balanced
        }

        // 兼容不同命名与嵌套返回
        if (parsed && !Array.isArray(parsed.headers)) {
          const candidateHeaders = parsed.headers || parsed.columns || parsed.fields || parsed?.table?.headers || parsed?.data?.headers
          if (Array.isArray(candidateHeaders)) parsed.headers = candidateHeaders
        }
        if (parsed && !Array.isArray(parsed.rows)) {
          const candidateRows = parsed.rows || parsed.data || parsed.entries || parsed.items || parsed?.table?.rows
          if (Array.isArray(candidateRows)) parsed.rows = candidateRows
        }

        if (!parsed || !Array.isArray(parsed.headers)) {
          throw new Error('LLM 未返回有效表格结构')
        }

        // 过滤可能被模型误放入 headers 的推理字段名
        const headers = parsed.headers.filter(
          (h) => h !== '__reasoning' && h !== 'reasoning' && h !== 'reason' && h !== 'rationale' && h !== 'explanation'
        )
        // 规范化行为对象数组
        const normalizedRows = Array.isArray(parsed.rows) ? parsed.rows.map((row) => {
          if (row && typeof row === 'object' && !Array.isArray(row)) {
            // 只保留 headers 中的字段
            const obj = {}
            headers.forEach((h) => {
              obj[h] = (row[h] ?? '').toString()
            })
            // 透传可选的行级推理字段（兼容常见别名）
            const reasoningKey = ['__reasoning', 'reasoning', 'reason', 'rationale', 'explanation'].find(
              (k) => Object.prototype.hasOwnProperty.call(row, k)
            )
            if (reasoningKey) {
              try { obj.__reasoning = (row[reasoningKey] ?? '').toString() } catch (_) { obj.__reasoning = '' }
            }
            return obj
          }
          // 如果是数组，按顺序映射到 headers
          if (Array.isArray(row)) {
            const obj = {}
            headers.forEach((h, idx) => {
              obj[h] = (row[idx] ?? '').toString()
            })
            return obj
          }
          return headers.reduce((acc, h) => ({ ...acc, [h]: '' }), {})
        }) : []

        const table = {
          id: Date.now(),
          title: parsed.title || '生成的表格',
          description: parsed.description || config.description || '',
          headers,
          rows: normalizedRows,
          totalRows: normalizedRows.length,
          generationStats: parsed.generationStats || { sourceDocuments: 0, averageConfidence: 0 },
          generatedAt: new Date().toISOString(),
          usedPrompt: userPrompt
        }

        commit('ADD_TABLE', table)
        commit('SET_CURRENT_TABLE', table)
        commit('SET_GENERATION_STATUS', 'completed')

        return table
      } catch (error) {
        console.error('表格生成失败:', error)
        const msg = String(error?.message || error || '未知错误')
        // 清理误导性的堆栈/提示词片段
        const cleanMsg = msg.includes('total_indicators') || msg.includes('extraction_summary')
          ? 'LLM 输出解析失败或后端异常，请查看控制台日志'
          : msg
        commit('SET_GENERATION_STATUS', 'failed')
        const cleanError = new Error(`表格生成失败: ${cleanMsg}`)
        cleanError.originalError = error
        throw cleanError
      }
    },

    // 获取表格列表
    async fetchTables({ commit }) {
      try {
        // TODO: 调用API获取表格列表
        const tables = []
        commit('SET_TABLES', tables)
        return tables
      } catch (error) {
        console.error('获取表格列表失败:', error)
        throw error
      }
    },

    // 保存表格
    async saveTable({ commit }, tableData) {
      try {
        // TODO: 调用API保存表格
        // const result = await saveTableAPI(tableData)

        const table = {
          ...tableData,
          id: tableData.id || Date.now(),
          savedAt: new Date().toISOString()
        }

        if (tableData.id) {
          commit('UPDATE_TABLE', { tableId: tableData.id, updates: table })
        } else {
          commit('ADD_TABLE', table)
        }

        return table
      } catch (error) {
        console.error('保存表格失败:', error)
        throw error
      }
    },

    // 删除表格
    async deleteTable({ commit }, tableId) {
      try {
        // TODO: 调用API删除表格
        // await deleteTableAPI(tableId)

        commit('REMOVE_TABLE', tableId)
      } catch (error) {
        console.error('删除表格失败:', error)
        throw error
      }
    },

    // 导出表格
    async exportTable({ state }, { tableId, format = 'xlsx' }) {
      try {
        const table = state.tables.find(t => t.id === tableId) || state.currentTable
        if (!table) {
          throw new Error('未找到要导出的表格')
        }

        // CSV 导出
        if (format === 'csv') {
          const csvHeaders = table.headers.join(',')
          const csvRows = table.rows.map(r => table.headers.map(h => `"${(r[h] ?? '').replace(/"/g, '""')}"`).join(',')).join('\n')
          const csvContent = [csvHeaders, csvRows].join('\n')
          const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
          const url = URL.createObjectURL(blob)
          const link = document.createElement('a')
          link.href = url
          link.download = `${table.title || 'table'}.csv`
          document.body.appendChild(link)
          link.click()
          document.body.removeChild(link)
          URL.revokeObjectURL(url)
          return true
        }

        // Excel 导出（需要 xlsx 依赖）
        if (format === 'xlsx') {
          try {
            const mod = await import('xlsx')
            const XLSX = mod?.default || mod
            const headerRow = table.headers
            const dataRows = table.rows.map(r => headerRow.map(h => r[h] ?? ''))
            const ws = XLSX.utils.aoa_to_sheet([headerRow, ...dataRows])
            const wb = XLSX.utils.book_new()
            XLSX.utils.book_append_sheet(wb, ws, 'Sheet1')
            XLSX.writeFile(wb, `${table.title || 'table'}.xlsx`)
            return true
          } catch (e) {
            throw new Error('未安装 xlsx 依赖，无法导出为 .xlsx。请运行 npm install xlsx')
          }
        }

        // PDF 导出（浏览器打印到 PDF）
        if (format === 'pdf') {
          const html = `<!DOCTYPE html><html><head><meta charset="utf-8"/>
          <title>${(table.title || '表格')}</title>
          <style>
            body{font-family: Arial, Helvetica, sans-serif;padding:16px;}
            h1{font-size:18px;margin:0 0 12px 0}
            table{border-collapse:collapse;width:100%;}
            th,td{border:1px solid #999;padding:6px 8px;font-size:12px;}
            th{background:#f5f5f5;text-align:left}
          </style></head><body>
          <h1>${(table.title || '表格')}</h1>
          <table><thead><tr>
          ${table.headers.map(h => `<th>${h}</th>`).join('')}
          </tr></thead><tbody>
          ${table.rows.map(r => `<tr>${table.headers.map(h => `<td>${(r[h] ?? '')}</td>`).join('')}</tr>`).join('')}
          </tbody></table>
          <script>window.onload = function(){window.print(); setTimeout(()=>window.close(), 300);};</script>
          </body></html>`
          const w = window.open('', '_blank')
          if (!w) throw new Error('浏览器阻止了弹窗，请允许弹窗后重试')
          w.document.open()
          w.document.write(html)
          w.document.close()
          return true
        }

        throw new Error('不支持的导出格式')
      } catch (error) {
        console.error('导出表格失败:', error)
        throw error
      }
    },

    // 设置当前表格
    setCurrentTable({ commit }, table) {
      commit('SET_CURRENT_TABLE', table)
    },

    // 清空当前表格
    clearCurrentTable({ commit }) {
      commit('SET_CURRENT_TABLE', null)
      commit('SET_GENERATION_STATUS', 'idle')
    },

    // 重置配置
    resetConfig({ commit }) {
      commit('RESET_TABLE_CONFIG')
      commit('SET_GENERATION_STATUS', 'idle')
    }
  },
  getters: {
    // 是否正在生成
    isGenerating: (state) => {
      return state.generationStatus === 'generating'
    },

    // 生成是否完成
    isCompleted: (state) => {
      return state.generationStatus === 'completed'
    },

    // 生成是否失败
    isFailed: (state) => {
      return state.generationStatus === 'failed'
    },

    // 表格统计
    tableStats: (state) => {
      return {
        total: state.tables.length,
        currentTableRows: state.currentTable?.totalRows || 0
      }
    }
  }
}