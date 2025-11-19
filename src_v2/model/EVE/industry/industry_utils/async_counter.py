# 标准库导入
import asyncio


class AsyncCounter():
    """异步计数器类，提供线程安全的计数功能"""
    
    def __init__(self):
        self.node_counter = 0
        self.relation_counter = 0
        self._lock = asyncio.Lock()
    
    async def next_node(self) -> int:
        """
        返回当前node计数并+1
        
        Returns:
            int: 返回当前的node_counter值，然后将其+1
        """
        async with self._lock:
            current = self.node_counter
            self.node_counter += 1
            return current
    
    async def next_relation(self) -> int:
        """
        返回当前relation计数并+1
        
        Returns:
            int: 返回当前的relation_counter值，然后将其+1
        """
        async with self._lock:
            current = self.relation_counter
            self.relation_counter += 1
            return current
    
    async def init_count(self):
        """
        重置所有计数器为0
        """
        async with self._lock:
            self.node_counter = 0
            self.relation_counter = 0

