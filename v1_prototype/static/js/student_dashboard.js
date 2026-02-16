document.addEventListener('DOMContentLoaded', function() {
    // Handle task completion and XP gains
    const taskItems = document.querySelectorAll('.task-item input[type="checkbox"]');
    const progressBar = document.querySelector('.progress');
    const xpCounter = document.querySelector('.progress-bar span');
    
    let currentXP = 750;
    const maxXP = 1000;

    taskItems.forEach(task => {
        task.addEventListener('change', function() {
            if (this.checked) {
                // Get XP value from the reward span
                const xpReward = parseInt(this.parentElement.parentElement.querySelector('.reward').textContent);
                
                // Animate XP gain
                animateXPGain(xpReward);
                
                // Add celebration effect
                createConfetti(this.parentElement);
                
                // Disable the task
                this.disabled = true;
            }
        });
    });

    function animateXPGain(xpAmount) {
        const startXP = currentXP;
        const endXP = Math.min(currentXP + xpAmount, maxXP);
        const duration = 1000; // 1 second
        const startTime = performance.now();

        function updateXP(currentTime) {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);

            const currentValue = startXP + (endXP - startXP) * progress;
            const percentage = (currentValue / maxXP) * 100;

            progressBar.style.width = percentage + '%';
            xpCounter.textContent = Math.round(currentValue) + '/' + maxXP + ' XP';

            if (progress < 1) {
                requestAnimationFrame(updateXP);
            } else {
                currentXP = endXP;
            }
        }

        requestAnimationFrame(updateXP);
    }

    function createConfetti(element) {
        const colors = ['#4a90e2', '#2ecc71', '#f1c40f', '#e74c3c'];
        
        for (let i = 0; i < 20; i++) {
            const confetti = document.createElement('div');
            confetti.className = 'confetti';
            
            const color = colors[Math.floor(Math.random() * colors.length)];
            confetti.style.backgroundColor = color;
            
            confetti.style.left = Math.random() * 100 + '%';
            confetti.style.animationDuration = (Math.random() * 1 + 1) + 's';
            confetti.style.opacity = Math.random();
            
            element.appendChild(confetti);
            
            setTimeout(() => {
                confetti.remove();
            }, 2000);
        }
    }

    // Add hover effects to badges
    const badges = document.querySelectorAll('.badge:not(.locked)');
    badges.forEach(badge => {
        badge.addEventListener('mouseover', function() {
            this.style.transform = 'scale(1.1) rotate(5deg)';
        });
        
        badge.addEventListener('mouseout', function() {
            this.style.transform = 'scale(1) rotate(0deg)';
        });
    });

    // Animate events on scroll
    const animateOnScroll = () => {
        const elements = document.querySelectorAll('.fade-in, .slide-in');
        elements.forEach(element => {
            const elementTop = element.getBoundingClientRect().top;
            const elementBottom = element.getBoundingClientRect().bottom;
            
            if (elementTop < window.innerHeight && elementBottom > 0) {
                element.style.opacity = '1';
                element.style.transform = 'translateX(0)';
            }
        });
    };

    // Initial check for animations
    animateOnScroll();
    
    // Listen for scroll events
    window.addEventListener('scroll', animateOnScroll);
});