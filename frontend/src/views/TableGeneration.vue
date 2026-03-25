<template>
  <div class="table-generation-container">
    <div class="table-layout">
      <!-- 左侧配置面板 -->
      <div class="config-panel">
        <a-card title="表格配置">
          <a-form layout="vertical">
            <a-form-item label="查询描述" required>
              <a-textarea v-model:value="tableConfig.query" placeholder="请描述您需要生成的表格内容，如：生成2019年绩效考核指标表（或其他细节：自定义列）" :rows="3" />
            </a-form-item>

            <a-form-item label="表格列定义">
              <div class="columns-config">
                <div v-for="(column, index) in tableConfig.columns" :key="index" class="column-item">
                  <a-input v-model:value="tableConfig.columns[index]" placeholder="列名" />
                  <a-button type="text" danger @click="removeColumn(index)" :disabled="tableConfig.columns.length <= 1">
                    <template #icon>
                      <delete-outlined />
                    </template>
                  </a-button>
                </div>

                <a-button type="dashed" block @click="addColumn">
                  <template #icon>
                    <plus-outlined />
                  </template>
                  添加列
                </a-button>
              </div>
            </a-form-item>

            <a-form-item label="最大行数">
              <a-input-number v-model:value="tableConfig.maxRows" :min="1" :max="500" style="width: 100%" />
            </a-form-item>

            <a-form-item label="表格描述">
              <a-textarea v-model:value="tableConfig.description" placeholder="可选，对表格的详细说明" :rows="2" />
            </a-form-item>

            <a-form-item label="推理过程显示">
              <a-switch v-model:checked="tableConfig.includeReasoning" />
              <span style="margin-left:8px;color:#8c8c8c;">开启后将在表格末尾追加“推理过程”列</span>
            </a-form-item>
          </a-form>

          <div class="action-buttons">
            <a-button type="primary" block :loading="isGenerating" :disabled="!canGenerate" @click="generateTable">
              <template #icon>
                <table-outlined />
              </template>
              生成表格
            </a-button>

            <a-button type="dashed" block :loading="isGenerating" @click="autoGenerateInitialTable">
              默认生成
            </a-button>

            <a-button block @click="resetConfig" :disabled="isGenerating">
              重置配置
            </a-button>
          </div>
        </a-card>
      </div>

      <!-- 右侧结果展示 -->
      <div class="result-panel">
        <!-- 生成中状态 -->
        <div v-if="isGenerating" class="generating-state">
          <a-spin size="large" />
          <div class="generating-text">
            <h3>正在生成表格</h3>
            <p>正在从文档中提取数据并构建表格，请稍候...</p>
          </div>
        </div>

        <!-- 表格结果 -->
        <div v-else-if="currentTable" class="table-result">
          <a-card>
            <template #title>
              <div class="table-header">
                <div class="table-title">
                  <table-outlined />
                  {{ currentTable.title }}
                </div>
                <div class="table-actions">
                  <a-dropdown>
                    <a-button>
                      <template #icon>
                        <download-outlined />
                      </template>
                      导出
                      <down-outlined />
                    </a-button>
                    <template #overlay>
                      <a-menu @click="handleExport">
                        <a-menu-item key="xlsx">Excel (.xlsx)</a-menu-item>
                        <a-menu-item key="csv">CSV (.csv)</a-menu-item>
                        <a-menu-item key="pdf">PDF (.pdf)</a-menu-item>
                      </a-menu>
                    </template>
                  </a-dropdown>

                  <a-button @click="saveTable">
                    <template #icon>
                      <save-outlined />
                    </template>
                    保存
                  </a-button>
                </div>
              </div>
            </template>

            <div class="table-info" v-if="currentTable.description">
              <p><strong>说明：</strong>{{ currentTable.description }}</p>
            </div>

            <div class="table-content">
              <a-table :rowKey="(record, index) => index" :columns="tableColumns" :data-source="currentTable.rows" :pagination="{
                pageSize: 20,
                showSizeChanger: true,
                showQuickJumper: true,
                showTotal: (total) => `共 ${total} 条记录`,
              }" :scroll="{ x: 'max-content' }" size="small" bordered>
                <!-- 动态渲染列内容 -->
                <template v-for="column in tableColumns" #[column.key]="{ text }" :key="column.key">
                  <span v-if="text">{{ text }}</span>
                  <span v-else class="empty-cell">-</span>
                </template>
              </a-table>
            </div>

            <div class="table-stats">
              <a-descriptions size="small" :column="4">
                <a-descriptions-item label="总行数">
                  {{ currentTable.totalRows }}
                </a-descriptions-item>
                <a-descriptions-item label="数据来源">
                  {{ currentTable.generationStats?.sourceDocuments || 0 }}
                  个文档
                </a-descriptions-item>
                <a-descriptions-item label="平均可信度">
                  {{
                    (
                      currentTable.generationStats?.averageConfidence * 100 || 0
                    ).toFixed(1)
                  }}%
                </a-descriptions-item>
                <a-descriptions-item label="生成时间">
                  {{ formatTime(currentTable.generatedAt) }}
                </a-descriptions-item>
              </a-descriptions>
            </div>
          </a-card>
        </div>

        <!-- 初始状态 -->
        <div v-else class="empty-state">
          <div class="empty-content">
            <table-outlined class="empty-icon" />
            <h3>开始生成您的表格</h3>
            <p>请在左侧配置表格参数，然后点击生成按钮</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { computed, reactive } from "vue";
import { useStore } from "vuex";
import { message } from "ant-design-vue";
import {
  TableOutlined,
  PlusOutlined,
  DeleteOutlined,
  DownloadOutlined,
  SaveOutlined,
  DownOutlined,
} from "@ant-design/icons-vue";
import dayjs from "dayjs";

export default {
  name: "TableGeneration",
  components: {
    TableOutlined,
    PlusOutlined,
    DeleteOutlined,
    DownloadOutlined,
    SaveOutlined,
    DownOutlined,
  },
  setup() {
    const store = useStore();

    // 表格配置
    const tableConfig = reactive({
      query: "",
      columns: ["项目名称", "负责部门", "完成时间", "备注"],
      maxRows: 100,
      description: "",
    });

    // 计算属性
    const isGenerating = computed(() => store.getters["table/isGenerating"]);
    const currentTable = computed(() => store.state.table.currentTable);

    const canGenerate = computed(() => {
      return tableConfig.query.trim() && tableConfig.columns.length > 0;
    });

    const tableColumns = computed(() => {
      if (!currentTable.value) return [];
      const base = currentTable.value.headers.map((header) => ({
        title: header,
        dataIndex: header,
        key: header,
        ellipsis: true,
        width: 150,
      }));
      if (tableConfig.includeReasoning) {
        base.push({
          title: '推理过程',
          dataIndex: '__reasoning',
          key: '__reasoning',
          ellipsis: true,
          width: 260,
        })
      }
      return base
    });

    // 生成请求复用函数
    const dispatchGeneration = async (payload, { backfillConfig } = { backfillConfig: false }) => {
      const result = await store.dispatch("table/generateTable", payload)
      if (!result || !result.headers) {
        throw new Error('未生成有效表格，请稍后重试或调整提示词。')
      }
      await store.dispatch('table/setCurrentTable', result)
      if (backfillConfig) {
        if (result.headers) tableConfig.columns = [...result.headers]
        if (result.usedPrompt) tableConfig.query = result.usedPrompt
      }
      return result
    }

    // 方法
    const autoGenerateInitialTable = async () => {
      try {
        await dispatchGeneration({
          query: "请自动从已入库文档中识别关键信息并生成一张最有用的汇总表（列名请自动识别与命名）",
          columns: [],
          maxRows: tableConfig.maxRows,
          description: "自动生成的初始表格，可在左侧修改配置后重新生成。",
          includeReasoning: tableConfig.includeReasoning,
        }, { backfillConfig: true })
      } catch (e) {
        message.error(e?.message || '默认生成失败')
      }
    }
    const addColumn = () => {
      tableConfig.columns.push("");
    };

    const removeColumn = (index) => {
      if (tableConfig.columns.length > 1) {
        tableConfig.columns.splice(index, 1);
      }
    };

    const generateTable = async () => {
      if (!canGenerate.value) {
        message.warning("请完善表格配置");
        return;
      }

      try {
        await dispatchGeneration({
          query: tableConfig.query,
          columns: tableConfig.columns.filter((col) => col.trim()),
          maxRows: tableConfig.maxRows,
          description: tableConfig.description,
          includeReasoning: tableConfig.includeReasoning,
        })
        message.success("表格生成成功");
      } catch (error) {
        message.error("生成表格失败：" + error.message);
      }
    };

    const resetConfig = () => {
      tableConfig.query = "";
      tableConfig.columns = ["项目名称", "负责部门", "完成时间", "备注"];
      tableConfig.maxRows = 100;
      tableConfig.description = "";

      store.dispatch("table/resetConfig");
    };

    const saveTable = async () => {
      if (!currentTable.value) return;

      try {
        await store.dispatch("table/saveTable", currentTable.value);
        message.success("表格保存成功");
      } catch (error) {
        message.error("保存失败：" + error.message);
      }
    };

    const handleExport = async ({ key }) => {
      if (!currentTable.value) return;

      try {
        await store.dispatch("table/exportTable", {
          tableId: currentTable.value.id,
          format: key,
        });
        message.success(`正在导出 ${key.toUpperCase()} 格式`);
      } catch (error) {
        message.error("导出失败：" + error.message);
      }
    };

    const formatTime = (timestamp) => {
      return dayjs(timestamp).format("YYYY-MM-DD HH:mm");
    };

    // 移除页面加载自动生成，改为手动点击“默认生成”触发

    return {
      tableConfig,
      isGenerating,
      currentTable,
      canGenerate,
      tableColumns,
      addColumn,
      removeColumn,
      generateTable,
      resetConfig,
      saveTable,
      handleExport,
      formatTime,
      autoGenerateInitialTable,
    };
  },
};
</script>

<style lang="less" scoped>
.table-generation-container {
  height: calc(100vh - 64px);
  background: #f0f2f5;
}

.table-layout {
  height: 100%;
  display: flex;
  padding: 16px 20px;
  gap: 16px;
}

.config-panel {
  width: 360px;
  position: sticky;
  top: 16px;
  align-self: flex-start;
  max-height: calc(100vh - 96px);
  overflow: auto;

  .columns-config {
    .column-item {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 8px;

      .ant-input {
        flex: 1;
      }
    }
  }

  .action-buttons {
    display: flex;
    flex-direction: column;
    gap: 12px;
    margin-top: 24px;
  }
}

.result-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: #fff;
  border-radius: 8px;
  padding: 12px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}

.generating-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: #fff;
  border-radius: 8px;

  .generating-text {
    margin-top: 24px;
    text-align: center;

    h3 {
      margin: 0 0 8px 0;
      font-size: 18px;
      color: #262626;
    }

    p {
      margin: 0;
      color: #8c8c8c;
    }
  }
}

.table-result {
  flex: 1;

  :deep(.ant-card) {
    height: 100%;
    display: flex;
    flex-direction: column;
    box-shadow: none;
    border: none;

    .ant-card-body {
      flex: 1;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      padding: 12px;
    }
  }

  .table-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    width: 100%;

    .table-title {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 16px;
      font-weight: 500;
    }

    .table-actions {
      display: flex;
      gap: 8px;
    }
  }

  .table-info {
    margin-bottom: 16px;
    padding: 12px;
    background: #f6f6f6;
    border-radius: 4px;

    p {
      margin: 0;
    }
  }

  .table-content {
    flex: 1;
    overflow: auto;
    background: #fff;
    border-radius: 6px;

    .empty-cell {
      color: #bfbfbf;
    }
  }

  .table-stats {
    margin-top: 16px;
    padding-top: 16px;
    border-top: 1px solid #f0f0f0;
  }
}

.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #fff;
  border-radius: 8px;
  box-shadow: none;
@media (max-width: 1200px) {
  .table-layout { flex-direction: column; padding: 12px; gap: 12px; }
  .config-panel { width: 100%; position: static; max-height: none; overflow: visible; }
}

@media (max-width: 768px) {
  .table-layout { padding: 8px; gap: 8px; }
  .result-panel { padding: 8px; }
}

  .empty-content {
    text-align: center;

    .empty-icon {
      font-size: 48px;
      color: #d9d9d9;
      margin-bottom: 16px;
    }

    h3 {
      margin: 0 0 8px 0;
      font-size: 16px;
      color: #595959;
    }

    p {
      margin: 0;
      color: #8c8c8c;
    }
  }
}
</style>
