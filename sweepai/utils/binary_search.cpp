#include <vector>

int binarySearch(const std::vector<int>& sortedArray, int target) {
    int left = 0;
    int right = sortedArray.size() - 1;
    
    while (left <= right) {
        int mid = left + (right - left) / 2;
        
        if (sortedArray[mid] == target) {
            return mid;
        }
        else if (sortedArray[mid] < target) {
            left = mid + 1;
        }
        else {
            right = mid - 1;
        }
    }
    
    return -1;  // target not found
}