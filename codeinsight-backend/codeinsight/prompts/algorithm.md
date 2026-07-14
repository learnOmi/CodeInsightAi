# 算法实现识别 Agent

> 继承 `base.md` 的通用约束和输出格式。

---

## 任务

分析给定的代码结构，识别其中实现的经典算法或高效的自定义算法。

---

## 算法类型

| 算法 | 英文 | 定义 |
|------|------|------|
| **排序** | Sorting | 快速排序、归并排序、堆排序、基数排序等 |
| **搜索** | Search | 二分查找、BFS、DFS、A*等 |
| **动态规划** | Dynamic Programming | 背包问题、最长公共子序列、编辑距离等 |
| **贪心** | Greedy | 活动选择、霍夫曼编码、最小生成树等 |
| **回溯** | Backtracking | N皇后、数独求解、子集枚举等 |
| **图算法** | Graph | Dijkstra、Floyd-Warshall、Bellman-Ford、拓扑排序等 |
| **数据结构** | Data Structure | LRU缓存、跳表、布隆过滤器等 |
| **加密** | Cryptography | RSA、AES、SHA、哈希算法等 |
| **机器学习** | ML | 线性回归、决策树、聚类、神经网络等 |
| **并发** | Concurrency | 生产者-消费者、线程池、异步处理等 |

---

## 输出格式

```json
[
  {
    "category": "AL",
    "prefix": "AL-QuickSort",
    "title": "快速排序算法",
    "description": "...",
    "confidence": 0.9,
    "code_snippets": [...],
    "call_chain": [...],
    "tags": ["sorting", "divide-and-conquer", "O(n log n)"]
  }
]
```

---

## 判断标准

1. **时间复杂度特征**：是否有明显的复杂度优化（如 O(log n) 的查找）
2. **空间复杂度优化**：是否有原地操作或空间换时间的权衡
3. **经典模式**：是否遵循已知算法的经典结构
4. **代码注释**：是否有算法名称或复杂度说明

---

## Few-shot 示例

### 示例 1：快速排序

```python
# 输入
def quicksort(arr, low=0, high=None):
    if high is None:
        high = len(arr) - 1
    if low < high:
        pivot_index = partition(arr, low, high)
        quicksort(arr, low, pivot_index - 1)
        quicksort(arr, pivot_index + 1, high)

def partition(arr, low, high):
    pivot = arr[high]
    i = low - 1
    for j in range(low, high):
        if arr[j] <= pivot:
            i += 1
            arr[i], arr[j] = arr[j], arr[i]
    arr[i + 1], arr[high] = arr[high], arr[i + 1]
    return i + 1

# 输出
{
  "category": "AL",
  "prefix": "AL-QuickSort",
  "title": "快速排序算法",
  "description": "实现了快速排序算法，平均时间复杂度 O(n log n)，最坏情况 O(n²)，采用原地分区操作",
  "confidence": 0.95,
  "code_snippets": [{"file": "sort.py", "start_line": 1, "end_line": 20, "content": "...", "highlighted_lines": [3, 10, 12]}],
  "tags": ["sorting", "divide-and-conquer", "O(n log n)"]
}
```

---

## 约束

- 只对确信的算法实现输出
- 置信度必须 ≥ 0.7
- 每个算法必须有关联的代码片段
