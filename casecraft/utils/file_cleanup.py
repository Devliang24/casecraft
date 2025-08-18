"""文件清理管理工具."""

import os
import glob
import shutil
import time
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import logging


class FileCleanupManager:
    """文件清理管理器."""
    
    def __init__(self, dry_run: bool = False, force: bool = False):
        """初始化文件清理管理器.
        
        Args:
            dry_run: 是否为预览模式，不实际删除文件
            force: 是否强制清理所有文件
        """
        self.dry_run = dry_run
        self.force = force
        self.logger = logging.getLogger("casecraft.cleanup")
        
    def clean_logs(self, log_dir: str = "logs", keep_days: int = 7, keep_count: int = 5) -> Dict[str, int]:
        """清理过期日志文件.
        
        Args:
            log_dir: 日志目录路径
            keep_days: 保留天数
            keep_count: 最少保留文件数
            
        Returns:
            清理统计信息
        """
        log_path = Path(log_dir)
        if not log_path.exists():
            self.logger.info(f"日志目录不存在: {log_path}")
            return {"deleted": 0, "kept": 0, "size_freed": 0}
        
        # 获取所有日志文件
        log_files = list(log_path.glob("*.log"))
        if not log_files:
            self.logger.info("没有找到日志文件")
            return {"deleted": 0, "kept": 0, "size_freed": 0}
        
        deleted_count = 0
        size_freed = 0
        
        if self.force:
            # 强制模式：删除所有日志文件
            for log_file in log_files:
                file_size = log_file.stat().st_size
                if self.dry_run:
                    self.logger.info(f"[预览] 将强制删除日志文件: {log_file} ({file_size} bytes)")
                else:
                    self.logger.info(f"强制删除日志文件: {log_file}")
                    log_file.unlink()
                deleted_count += 1
                size_freed += file_size
        else:
            # 按修改时间排序（最新的在前）
            log_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            
            cutoff_time = time.time() - (keep_days * 24 * 3600)
            
            # 保留最新的 keep_count 个文件
            files_to_check = log_files[keep_count:]
            
            for log_file in files_to_check:
                if log_file.stat().st_mtime < cutoff_time:
                    file_size = log_file.stat().st_size
                    if self.dry_run:
                        self.logger.info(f"[预览] 将删除日志文件: {log_file} ({file_size} bytes)")
                    else:
                        self.logger.info(f"删除过期日志文件: {log_file}")
                        log_file.unlink()
                    deleted_count += 1
                    size_freed += file_size
        
        kept_count = len(log_files) - deleted_count
        
        self.logger.info(f"日志清理完成: 删除 {deleted_count} 个文件, 保留 {kept_count} 个, 释放 {size_freed} bytes")
        return {"deleted": deleted_count, "kept": kept_count, "size_freed": size_freed}
    
    def clean_test_cases(self, test_dir: str = "test_cases") -> Dict[str, int]:
        """清理重复的测试用例文件.
        
        Args:
            test_dir: 测试用例目录路径
            
        Returns:
            清理统计信息
        """
        test_path = Path(test_dir)
        if not test_path.exists():
            self.logger.info(f"测试用例目录不存在: {test_path}")
            return {"deleted": 0, "kept": 0, "size_freed": 0}
        
        size_freed = 0
        deleted_count = 0
        
        if self.force:
            # 强制模式：删除所有JSON文件（保留.gitkeep）
            json_files = list(test_path.glob("*.json"))
            for json_file in json_files:
                file_size = json_file.stat().st_size
                if self.dry_run:
                    self.logger.info(f"[预览] 将强制删除测试文件: {json_file} ({file_size} bytes)")
                else:
                    self.logger.info(f"强制删除测试文件: {json_file}")
                    json_file.unlink()
                deleted_count += 1
                size_freed += file_size
            kept_count = 0
        else:
            # 查找带时间戳的重复文件
            patterns = [
                "*_[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]_[0-9][0-9][0-9][0-9][0-9][0-9].json"
            ]
            
            file_groups = {}
            
            for pattern in patterns:
                files = list(test_path.glob(pattern))
                
                # 按基础名称分组
                for file in files:
                    # 提取基础名称（去掉时间戳）
                    base_name = file.name.split('_202')[0]  # 假设时间戳以202开头
                    if base_name not in file_groups:
                        file_groups[base_name] = []
                    file_groups[base_name].append(file)
            
            # 对每组文件，只保留最新的
            for base_name, files in file_groups.items():
                if len(files) <= 1:
                    continue
                    
                # 按修改时间排序，保留最新的
                files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
                files_to_delete = files[1:]  # 删除除最新外的所有文件
            
                for file in files_to_delete:
                    file_size = file.stat().st_size
                    if self.dry_run:
                        self.logger.info(f"[预览] 将删除重复文件: {file} ({file_size} bytes)")
                    else:
                        self.logger.info(f"删除重复测试文件: {file}")
                        file.unlink()
                    deleted_count += 1
                    size_freed += file_size
            
            kept_count = sum(1 for group in file_groups.values() if group)
        
        self.logger.info(f"测试用例清理完成: 删除 {deleted_count} 个重复文件, 保留 {kept_count} 组, 释放 {size_freed} bytes")
        return {"deleted": deleted_count, "kept": kept_count, "size_freed": size_freed}
    
    def clean_debug_files(self, debug_dir: str = "debug_responses", archive_days: int = 30) -> Dict[str, int]:
        """清理调试文件.
        
        Args:
            debug_dir: 调试文件目录
            archive_days: 归档天数
            
        Returns:
            清理统计信息
        """
        debug_path = Path(debug_dir)
        if not debug_path.exists():
            self.logger.info(f"调试目录不存在: {debug_path}")
            return {"archived": 0, "deleted": 0, "size_freed": 0}
        
        archive_path = debug_path / "archive"
        archive_path.mkdir(exist_ok=True)
        
        # 查找调试文件
        debug_files = list(debug_path.glob("*.json"))
        cutoff_time = time.time() - (archive_days * 24 * 3600)
        
        archived_count = 0
        deleted_count = 0
        size_freed = 0
        
        for file in debug_files:
            file_age = time.time() - file.stat().st_mtime
            
            if file_age > cutoff_time:
                # 删除过期的归档文件
                file_size = file.stat().st_size
                if self.dry_run:
                    self.logger.info(f"[预览] 将删除过期调试文件: {file} ({file_size} bytes)")
                else:
                    self.logger.info(f"删除过期调试文件: {file}")
                    file.unlink()
                deleted_count += 1
                size_freed += file_size
            else:
                # 归档较新的文件
                if self.dry_run:
                    self.logger.info(f"[预览] 将归档调试文件: {file}")
                else:
                    archive_file = archive_path / file.name
                    if not archive_file.exists():
                        shutil.move(str(file), str(archive_file))
                        self.logger.info(f"归档调试文件: {file} -> {archive_file}")
                        archived_count += 1
        
        self.logger.info(f"调试文件处理完成: 归档 {archived_count} 个, 删除 {deleted_count} 个, 释放 {size_freed} bytes")
        return {"archived": archived_count, "deleted": deleted_count, "size_freed": size_freed}
    
    def auto_cleanup(self) -> Dict[str, Dict[str, int]]:
        """执行自动清理任务.
        
        Returns:
            所有清理任务的统计信息
        """
        self.logger.info("开始执行自动文件清理...")
        
        results = {
            "logs": self.clean_logs(),
            "test_cases": self.clean_test_cases(), 
            "debug_files": self.clean_debug_files()
        }
        
        # 计算总计
        total_deleted = sum(r.get("deleted", 0) for r in results.values())
        total_size_freed = sum(r.get("size_freed", 0) for r in results.values())
        
        self.logger.info(f"自动清理完成: 总共删除 {total_deleted} 个文件, 释放 {total_size_freed} bytes")
        
        return results
    
    def get_cleanup_summary(self) -> Dict[str, any]:
        """获取可清理文件的摘要信息.
        
        Returns:
            清理摘要信息
        """
        summary = {
            "logs": {"count": 0, "size": 0, "oldest": None},
            "test_cases": {"duplicates": 0, "size": 0},
            "debug_files": {"count": 0, "size": 0}
        }
        
        # 检查日志文件
        log_path = Path("logs")
        if log_path.exists():
            log_files = list(log_path.glob("*.log"))
            if log_files:
                summary["logs"]["count"] = len(log_files)
                summary["logs"]["size"] = sum(f.stat().st_size for f in log_files)
                oldest_file = min(log_files, key=lambda f: f.stat().st_mtime)
                summary["logs"]["oldest"] = datetime.fromtimestamp(oldest_file.stat().st_mtime)
        
        # 检查测试用例重复文件
        test_path = Path("test_cases")
        if test_path.exists():
            timestamped_files = list(test_path.glob("*_[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]_*.json"))
            summary["test_cases"]["duplicates"] = len(timestamped_files)
            summary["test_cases"]["size"] = sum(f.stat().st_size for f in timestamped_files)
        
        # 检查调试文件
        debug_path = Path("debug_responses")
        if debug_path.exists():
            debug_files = list(debug_path.glob("*.json"))
            summary["debug_files"]["count"] = len(debug_files)
            summary["debug_files"]["size"] = sum(f.stat().st_size for f in debug_files)
        
        return summary