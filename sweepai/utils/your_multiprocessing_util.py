import multiprocessing


def safe_multiprocessing_pool_initializer():
    desired_number_of_processes = multiprocessing.cpu_count()
    safe_number_of_processes = max(1, desired_number_of_processes)
    pool = multiprocessing.Pool(processes=safe_number_of_processes)
    return pool

def task_function(data):
    # Placeholder for a task that would be executed by the pool
    return data * 2

def execute_tasks_in_pool(data_list):
    pool = safe_multiprocessing_pool_initializer()
    results = pool.map(task_function, data_list)
    pool.close()
    pool.join()
    return results

# Unit tests
import unittest
from unittest.mock import patch


class TestSafeMultiprocessingPoolInitializer(unittest.TestCase):
    @patch('multiprocessing.cpu_count', return_value=0)
    def test_cpu_count_zero(self, mock_cpu_count):
        pool = safe_multiprocessing_pool_initializer()
        self.assertIsNotNone(pool)
        pool.terminate()

    @patch('multiprocessing.cpu_count', return_value=1)
    def test_cpu_count_one(self, mock_cpu_count):
        pool = safe_multiprocessing_pool_initializer()
        self.assertIsNotNone(pool)
        pool.terminate()

    @patch('multiprocessing.cpu_count', return_value=4)
    def test_cpu_count_multiple(self, mock_cpu_count):
        pool = safe_multiprocessing_pool_initializer()
        self.assertIsNotNone(pool)
        pool.terminate()

    def test_execute_tasks_in_pool(self):
        data_list = [1, 2, 3, 4, 5]
        expected_results = [2, 4, 6, 8, 10]
        results = execute_tasks_in_pool(data_list)
        self.assertEqual(results, expected_results)

if __name__ == '__main__':
    unittest.main()
