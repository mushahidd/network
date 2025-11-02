// Theme switcher with localStorage persistence
(function() {
    const THEME_KEY = 'connecthub-theme';
    const THEME_DARK = 'dark';
    const THEME_LIGHT = 'light';
    
    // Get saved theme or default to light
    function getSavedTheme() {
        const saved = localStorage.getItem(THEME_KEY);
        if (saved) return saved;
        
        // Check system preference
        if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
            return THEME_DARK;
        }
        return THEME_LIGHT;
    }
    
    // Apply theme to document
    function applyTheme(theme) {
        const html = document.documentElement;
        
        if (theme === THEME_DARK) {
            html.classList.add('dark');
            html.setAttribute('data-theme', 'dark');
        } else {
            html.classList.remove('dark');
            html.setAttribute('data-theme', 'light');
        }
        
        // Update toggle button
        updateToggleButton(theme);
    }
    
    // Update toggle button appearance
    function updateToggleButton(theme) {
        const toggle = document.getElementById('theme-toggle');
        const sunIcon = document.getElementById('sun-icon');
        const moonIcon = document.getElementById('moon-icon');
        
        if (!toggle || !sunIcon || !moonIcon) return;
        
        if (theme === THEME_DARK) {
            sunIcon.classList.remove('hidden');
            moonIcon.classList.add('hidden');
            toggle.setAttribute('aria-label', 'Switch to light mode');
        } else {
            sunIcon.classList.add('hidden');
            moonIcon.classList.remove('hidden');
            toggle.setAttribute('aria-label', 'Switch to dark mode');
        }
    }
    
    // Toggle theme
    function toggleTheme() {
        const currentTheme = getSavedTheme();
        const newTheme = currentTheme === THEME_DARK ? THEME_LIGHT : THEME_DARK;
        
        localStorage.setItem(THEME_KEY, newTheme);
        applyTheme(newTheme);
        
        // Add animation class
        const toggle = document.getElementById('theme-toggle');
        if (toggle) {
            toggle.classList.add('theme-toggle-spin');
            setTimeout(() => {
                toggle.classList.remove('theme-toggle-spin');
            }, 500);
        }
    }
    
    // Initialize theme on page load
    function initTheme() {
        const theme = getSavedTheme();
        applyTheme(theme);
        
        // Add click listener to toggle button
        const toggle = document.getElementById('theme-toggle');
        if (toggle) {
            toggle.addEventListener('click', toggleTheme);
        }
    }
    
    // Apply theme immediately (before page renders)
    applyTheme(getSavedTheme());
    
    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initTheme);
    } else {
        initTheme();
    }
    
    // Listen for system theme changes
    if (window.matchMedia) {
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => {
            if (!localStorage.getItem(THEME_KEY)) {
                applyTheme(e.matches ? THEME_DARK : THEME_LIGHT);
            }
        });
    }
})();
