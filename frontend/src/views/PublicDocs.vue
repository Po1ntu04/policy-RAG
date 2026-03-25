<template>
  <div class="public-docs-container">
    <div class="docs-layout">
      <div class="filter-panel">
        <a-card title="筛选条件" size="small">
          <a-form layout="vertical" size="small">
            <a-form-item label="年份">
              <a-select
                v-model:value="filters.year"
                allow-clear
                placeholder="选择年份"
              >
                <a-select-option
                  v-for="year in yearOptions"
                  :key="year"
                  :value="year"
                >
                  {{ year }}年
                </a-select-option>
              </a-select>
            </a-form-item>

            <a-form-item label="责任单位">
              <a-select
                v-model:value="filters.responsibleUnit"
                allow-clear
                show-search
                placeholder="选择责任单位"
              >
                <a-select-option
                  v-for="unit in unitOptions"
                  :key="unit"
                  :value="unit"
                >
                  {{ unit }}
                </a-select-option>
              </a-select>
            </a-form-item>

            <a-form-item label="责任部门">
              <a-select
                v-model:value="filters.responsibleDepartment"
                allow-clear
                show-search
                placeholder="选择责任部门"
              >
                <a-select-option
                  v-for="dept in departmentOptions"
                  :key="dept"
                  :value="dept"
                >
                  {{ dept }}
                </a-select-option>
              </a-select>
            </a-form-item>
          </a-form>

          <div class="filter-actions">
            <a-button type="primary" block @click="handleSearch">
              <template #icon><search-outlined /></template>
              搜索
            </a-button>
            <a-button block @click="resetFilters">重置</a-button>
          </div>
        </a-card>

        <a-card title="排序偏好" size="small" style="margin-top: 16px">
          <a-form layout="vertical" size="small">
            <a-form-item label="排序方式">
              <a-select v-model:value="filters.sortBy">
                <a-select-option value="hot">热门</a-select-option>
                <a-select-option value="likes">点赞量</a-select-option>
                <a-select-option value="follows">关注度</a-select-option>
                <a-select-option value="comments">评论数</a-select-option>
                <a-select-option value="relevance">相关度</a-select-option>
                <a-select-option value="publish_date">发布时间</a-select-option>
              </a-select>
            </a-form-item>
            <a-form-item label="排序方向">
              <a-select v-model:value="filters.sortDir">
                <a-select-option value="desc">从高到低</a-select-option>
                <a-select-option value="asc">从低到高</a-select-option>
              </a-select>
            </a-form-item>
          </a-form>
        </a-card>
      </div>

      <div class="main-panel">
        <div class="toolbar">
          <a-input-search
            v-model:value="filters.keyword"
            placeholder="关键词搜索（标题/文件名）"
            allow-clear
            @search="handleSearch"
            style="max-width: 420px"
          />
          <div class="toolbar-right">
            <a-space>
              <span class="ai-hint">AI筛选TopK</span>
              <a-switch v-model:checked="filters.aiRerank" />
              <a-input-number
                v-model:value="filters.rerankK"
                :min="5"
                :max="100"
                style="width: 90px"
              />
            </a-space>
          </div>
        </div>

        <a-list
          :data-source="docs"
          :loading="loading"
          item-layout="vertical"
          :locale="{ emptyText: '暂无公开文件' }"
          class="docs-list"
        >
          <template #renderItem="{ item }">
            <a-list-item class="doc-item">
              <div class="doc-main">
                <div class="doc-title">
                  <a class="doc-link" @click="viewDetail(item)">{{ item.title }}</a>
                  <a-tag color="blue" v-if="item.publish_date">
                    {{ formatDate(item.publish_date) }}
                  </a-tag>
                </div>
                <div class="doc-meta">
                  <span class="doc-file">{{ item.file_name || '未命名文件' }}</span>
                  <span class="doc-stats">
                    <like-outlined /> {{ item.likes_count }}
                    <star-outlined /> {{ item.follows_count }}
                    <message-outlined /> {{ item.comments_count }}
                  </span>
                </div>
              </div>

              <template #actions>
                <a-space>
                  <a-button type="text" size="small" @click="toggleLike(item)">
                    <template #icon>
                      <like-filled v-if="item.user_liked" />
                      <like-outlined v-else />
                    </template>
                    点赞
                  </a-button>
                  <a-button type="text" size="small" @click="toggleFollow(item)">
                    <template #icon>
                      <star-filled v-if="item.user_followed" />
                      <star-outlined v-else />
                    </template>
                    关注
                  </a-button>
                  <a-button type="text" size="small" @click="viewDetail(item)">
                    <template #icon><message-outlined /></template>
                    互动详情
                  </a-button>
                  <a-button type="primary" size="small" @click="askAboutDoc(item)">
                    <template #icon><question-circle-outlined /></template>
                    针对提问
                  </a-button>
                </a-space>
              </template>
            </a-list-item>
          </template>
        </a-list>

        <div class="pagination">
          <a-pagination
            :current="pagination.current"
            :page-size="pagination.pageSize"
            :total="pagination.total"
            show-size-changer
            show-quick-jumper
            @change="handlePageChange"
            @showSizeChange="handlePageChange"
          />
        </div>
      </div>
    </div>

  </div>
</template>

<script>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  SearchOutlined,
  LikeOutlined,
  LikeFilled,
  StarOutlined,
  StarFilled,
  MessageOutlined,
  QuestionCircleOutlined
} from '@ant-design/icons-vue'
import api from '@/services/api'
import dayjs from 'dayjs'

export default {
  name: 'PublicDocs',
  components: {
    SearchOutlined,
    LikeOutlined,
    LikeFilled,
    StarOutlined,
    StarFilled,
    MessageOutlined,
    QuestionCircleOutlined
  },
  setup() {
    const router = useRouter()
    const loading = ref(false)
    const docs = ref([])
    const yearOptions = ref([])
    const unitOptions = ref([])
    const departmentOptions = ref([])

    const filters = reactive({
      year: null,
      responsibleUnit: null,
      responsibleDepartment: null,
      keyword: '',
      sortBy: 'hot',
      sortDir: 'desc',
      aiRerank: false,
      rerankK: 30
    })

    const pagination = reactive({
      current: 1,
      pageSize: 10,
      total: 0
    })

    const fetchFilters = async () => {
      try {
        const resp = await api.get('/public/docs/filters')
        yearOptions.value = resp.years || []
        unitOptions.value = resp.responsible_units || []
        departmentOptions.value = resp.responsible_departments || []
      } catch (error) {
        console.error('获取筛选项失败:', error)
      }
    }

    const fetchDocs = async () => {
      loading.value = true
      try {
        const params = {
          skip: (pagination.current - 1) * pagination.pageSize,
          limit: pagination.pageSize,
          sort_by: filters.sortBy,
          sort_dir: filters.sortDir
        }
        if (filters.year) params.year = filters.year
        if (filters.responsibleUnit) params.responsible_unit = filters.responsibleUnit
        if (filters.responsibleDepartment) params.responsible_department = filters.responsibleDepartment
        if (filters.keyword) params.keyword = filters.keyword
        if (filters.aiRerank && filters.keyword) {
          params.ai_rerank = true
          params.rerank_k = filters.rerankK
        }
        const resp = await api.get('/public/docs', { params })
        docs.value = resp.items || []
        pagination.total = resp.total || 0
      } catch (error) {
        message.error('获取公开文件失败：' + error.message)
      } finally {
        loading.value = false
      }
    }

    const handleSearch = () => {
      pagination.current = 1
      fetchDocs()
    }

    const resetFilters = () => {
      filters.year = null
      filters.responsibleUnit = null
      filters.responsibleDepartment = null
      filters.keyword = ''
      filters.sortBy = 'hot'
      filters.sortDir = 'desc'
      filters.aiRerank = false
      filters.rerankK = 30
      pagination.current = 1
      fetchDocs()
    }

    const handlePageChange = (page, pageSize) => {
      pagination.current = page
      pagination.pageSize = pageSize
      fetchDocs()
    }

    const toggleLike = async (item) => {
      try {
        const url = `/public/docs/${item.policy_id}/like`
        const resp = item.user_liked ? await api.delete(url) : await api.post(url)
        item.user_liked = !item.user_liked
        item.likes_count = resp.likes_count ?? item.likes_count
      } catch (error) {
        message.error('操作失败：' + error.message)
      }
    }

    const toggleFollow = async (item) => {
      try {
        const url = `/public/docs/${item.policy_id}/follow`
        const resp = item.user_followed ? await api.delete(url) : await api.post(url)
        item.user_followed = !item.user_followed
        item.follows_count = resp.follows_count ?? item.follows_count
      } catch (error) {
        message.error('操作失败：' + error.message)
      }
    }

    const viewDetail = (item) => {
      router.push(`/public-docs/${item.policy_id}`)
    }

    const askAboutDoc = (item) => {
      const docId = item.doc_ids?.[0]
      if (!docId) {
        message.warning('该文件尚未建立文档索引')
        return
      }
      router.push({
        path: '/chat',
        query: {
          doc_id: docId,
          doc_name: item.title || item.file_name || ''
        }
      })
    }

    const formatDate = (value) => {
      return value ? dayjs(value).format('YYYY-MM-DD') : '-'
    }

    onMounted(() => {
      fetchFilters()
      fetchDocs()
    })

    return {
      loading,
      docs,
      yearOptions,
      unitOptions,
      departmentOptions,
      filters,
      pagination,
      handleSearch,
      resetFilters,
      handlePageChange,
      toggleLike,
      toggleFollow,
      viewDetail,
      askAboutDoc,
      formatDate
    }
  }
}
</script>

<style lang="less" scoped>
.public-docs-container {
  height: 100%;
  padding: 16px;
  background: #f5f5f5;
}

.docs-layout {
  display: flex;
  gap: 16px;
  height: 100%;
}

.filter-panel {
  width: 280px;
  flex-shrink: 0;
}

.filter-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 16px;
}

.main-panel {
  flex: 1;
  min-width: 0;
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  display: flex;
  flex-direction: column;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.toolbar-right {
  display: flex;
  align-items: center;
}

.ai-hint {
  color: #666;
  font-size: 12px;
}

.docs-list {
  flex: 1;
  overflow: auto;
}

.doc-item {
  padding: 12px 8px;
}

.doc-main {
  width: 100%;
}

.doc-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
}

.doc-link {
  color: #262626;
  cursor: pointer;
}

.doc-link:hover {
  color: #1677ff;
}

.doc-meta {
  margin-top: 6px;
  display: flex;
  justify-content: space-between;
  color: #666;
  font-size: 13px;
}

.doc-file {
  max-width: 60%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.doc-stats {
  display: flex;
  gap: 12px;
  align-items: center;
  color: #8c8c8c;
}

.pagination {
  margin-top: 16px;
  text-align: right;
}

</style>
