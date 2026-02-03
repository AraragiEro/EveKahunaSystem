import { ref } from 'vue'
import { http } from '@/http'
import { ElMessage } from 'element-plus'
import type { SearchResult, TypeItem, AuxiliaryCondition } from '@/views/enterprise/types/market'

/**
 * 市场搜索功能 composable
 */
export function useMarketSearch() {
  // 状态
  const searchType = ref('group')
  const searchKeyword = ref('')
  const searchResults = ref<SearchResult[]>([])
  const selectedSearchResults = ref<SearchResult[]>([])
  const searchLoading = ref(false)
  const auxiliaryConditions = ref<AuxiliaryCondition[]>([])
  let auxiliaryConditionIdCounter = 0

  // 获取自动补全建议
  const fetchSearchSuggestions = async (queryString: string, cb: (suggestions: TypeItem[]) => void) => {
    if (searchType.value === 'typename') {
      // typename类型使用getTypeSuggestionsList API
      try {
        const res = await http.post('/EVE/industry/getTypeSuggestionsList', {
          type_name: queryString
        })
        const data = await res.json()
        const results = queryString ? (data.data || []).map((item: any) => ({ value: item.value || item.label || item })) : []
        cb(results)
      } catch (e) {
        cb([])
      }
    } else {
      // 其他类型使用getGroupSuggestions API
      try {
        const res = await http.post('/EVE/industry/getGroupSuggestions', {
          assign_type: searchType.value,
          query: queryString
        })
        const data = await res.json()
        const results = queryString ? (data.data || []).map((item: any) => ({ value: item.value || item.label || item })) : []
        cb(results)
      } catch (e) {
        cb([])
      }
    }
  }

  // 获取辅助条件的自动补全建议
  const fetchAuxiliarySuggestions = async (queryString: string, condition: AuxiliaryCondition, cb: (suggestions: TypeItem[]) => void): Promise<void> => {
    if (condition.searchType === 'typename') {
      // typename类型使用getTypeSuggestionsList API
      try {
        const res = await http.post('/EVE/industry/getTypeSuggestionsList', {
          type_name: queryString
        })
        const data = await res.json()
        const results = queryString ? (data.data || []).map((item: any) => ({ value: item.value || item.label || item })) : []
        cb(results)
      } catch (e) {
        cb([])
      }
    } else {
      // 其他类型使用getGroupSuggestions API
      try {
        const res = await http.post('/EVE/industry/getGroupSuggestions', {
          assign_type: condition.searchType,
          query: queryString
        })
        const data = await res.json()
        const results = queryString ? (data.data || []).map((item: any) => ({ value: item.value || item.label || item })) : []
        cb(results)
      } catch (e) {
        cb([])
      }
    }
  }

  // 为辅助条件创建类型化的获取建议函数
  const createAuxiliarySuggestionsFetcher = (condition: AuxiliaryCondition) => {
    return (queryString: string, cb: (suggestions: TypeItem[]) => void) => {
      fetchAuxiliarySuggestions(queryString, condition, cb)
    }
  }

  // 执行搜索
  const handleSearch = async () => {
    if (!searchKeyword.value.trim()) {
      ElMessage.warning('请输入搜索关键字')
      return
    }

    searchLoading.value = true
    try {
      // 构建辅助条件数组，过滤掉空的关键字
      const auxiliaryConditionsData = auxiliaryConditions.value
        .filter(condition => condition.keyword.trim())
        .map(condition => ({
          search_type: condition.searchType,
          keyword: condition.keyword.trim()
        }))

      const res = await http.post('/enterprise/market/search', {
        search_type: searchType.value,
        keyword: searchKeyword.value.trim(),
        auxiliary_conditions: auxiliaryConditionsData
      })
      const data = await res.json()

      if (data.status === 400 && data.count >= 2000) {
        ElMessage.warning(data.message || '匹配结果超过2000个，请缩小搜索范围')
        searchResults.value = data.data || []
        selectedSearchResults.value = []
      } else if (data.status === 200) {
        searchResults.value = data.data || []
        selectedSearchResults.value = []
        if (searchResults.value.length === 0) {
          ElMessage.info('未找到匹配的结果')
        }
      } else {
        ElMessage.error(data.message || '搜索失败')
        searchResults.value = []
        selectedSearchResults.value = []
      }
    } catch (e) {
      ElMessage.error('搜索失败')
      searchResults.value = []
      selectedSearchResults.value = []
    } finally {
      searchLoading.value = false
    }
  }

  // 添加辅助条件组
  const addAuxiliaryGroup = () => {
    auxiliaryConditions.value.push({
      id: ++auxiliaryConditionIdCounter,
      searchType: 'group',
      keyword: ''
    })
  }

  // 删除辅助条件组
  const removeAuxiliaryGroup = (id: number) => {
    const index = auxiliaryConditions.value.findIndex(item => item.id === id)
    if (index !== -1) {
      auxiliaryConditions.value.splice(index, 1)
    }
  }

  // 重置搜索状态
  const resetSearch = () => {
    searchType.value = 'group'
    searchKeyword.value = ''
    searchResults.value = []
    selectedSearchResults.value = []
    auxiliaryConditions.value = []
  }

  return {
    // 状态
    searchType,
    searchKeyword,
    searchResults,
    selectedSearchResults,
    searchLoading,
    auxiliaryConditions,
    // 方法
    fetchSearchSuggestions,
    fetchAuxiliarySuggestions,
    createAuxiliarySuggestionsFetcher,
    handleSearch,
    addAuxiliaryGroup,
    removeAuxiliaryGroup,
    resetSearch
  }
}
