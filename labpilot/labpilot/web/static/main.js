// LabPilot Dashboard JavaScript
// Handles frontend interactions for the experiment dashboard

document.addEventListener('DOMContentLoaded', function() {
    // Auto-refresh functionality
    const refreshInterval = 10000; // 10 seconds
    
    // Set up periodic refresh for experiments table
    setInterval(function() {
        const experimentsTable = document.getElementById('experimentsTable');
        if (experimentsTable) {
            experimentsTable.setAttribute('hx-get', '/experiments');
            experimentsTable.setAttribute('hx-trigger', 'every 10s');
        }
    }, refreshInterval);
    
    // Set up periodic refresh for stats
    setInterval(function() {
        const statsDiv = document.querySelector('.stats');
        if (statsDiv) {
            statsDiv.setAttribute('hx-get', '/experiments/stats');
            statsDiv.setAttribute('hx-trigger', 'every 30s');
        }
    }, 30000); // 30 seconds for stats
    
    // Search functionality with debounce
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        let searchTimeout;
        searchInput.addEventListener('input', function() {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                // Trigger search when user stops typing
                htmx.trigger(searchInput, 'keyup');
            }, 500);
        });
    }
    
    // Status filter functionality
    const statusFilter = document.getElementById('statusFilter');
    if (statusFilter) {
        statusFilter.addEventListener('change', function() {
            // Update the experiments table based on filter
            htmx.ajax('GET', '/experiments', {target: '#experimentsTable'});
        });
    }
    
    // Server filter functionality
    const serverFilter = document.getElementById('serverFilter');
    if (serverFilter) {
        serverFilter.addEventListener('change', function() {
            // Update the experiments table based on filter
            htmx.ajax('GET', '/experiments', {target: '#experimentsTable'});
        });
    }
    
    // Reset button functionality
    const resetButton = document.querySelector('button[onclick*="hx-vals"]');
    if (resetButton) {
        resetButton.addEventListener('click', function() {
            document.getElementById('searchInput').value = '';
            document.getElementById('statusFilter').value = '';
            document.getElementById('serverFilter').value = '';
        });
    }
});

// Utility function to format duration from seconds to human-readable format
function formatDuration(seconds) {
    if (!seconds) return 'N/A';
    
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    
    if (h > 0) {
        return `${h}h ${m}m ${s}s`;
    } else if (m > 0) {
        return `${m}m ${s}s`;
    } else {
        return `${s}s`;
    }
}

// Utility function to truncate text
function truncateText(text, maxLength = 100) {
    if (!text) return '';
    if (text.length <= maxLength) return text;
    return text.substr(0, maxLength) + '...';
}