// Generic modal helpers used across donors / donations / projects / expenses pages
function openModal(id) {
    const modal = document.getElementById(id);
    if (modal) modal.classList.add('open');
}

function closeModal(id) {
    const modal = document.getElementById(id);
    if (modal) modal.classList.remove('open');
}

// Close modal when clicking the dark overlay (outside the box)
document.addEventListener('click', (e) => {
    if (e.target.classList && e.target.classList.contains('modal')) {
        e.target.classList.remove('open');
    }
});

// Close modal with Escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        document.querySelectorAll('.modal.open').forEach(m => m.classList.remove('open'));
    }
});

// Auto-dismiss flash messages after 6 seconds
document.addEventListener('DOMContentLoaded', () => {
    setTimeout(() => {
        document.querySelectorAll('.flash').forEach(f => {
            f.style.transition = 'opacity 0.4s ease';
            f.style.opacity = '0';
            setTimeout(() => f.remove(), 400);
        });
    }, 6000);
});
