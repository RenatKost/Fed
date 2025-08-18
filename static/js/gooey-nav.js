// Gooey Navigation Effect
class GooeyNav {
    constructor() {
        this.init();
    }

    init() {
        this.createGooeyEffect();
        this.addEventListeners();
        this.highlightCurrentPage();
    }

    createGooeyEffect() {
        // Добавляем SVG фильтр для gooey эффекта
        const svgFilter = `
            <svg style="position: absolute; width: 0; height: 0;">
                <defs>
                    <filter id="gooey">
                        <feGaussianBlur in="SourceGraphic" stdDeviation="10" result="blur"/>
                        <feColorMatrix in="blur" mode="matrix" values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 19 -9" result="gooey"/>
                        <feComposite in="SourceGraphic" in2="gooey" operator="atop"/>
                    </filter>
                </defs>
            </svg>
        `;
        
        document.body.insertAdjacentHTML('afterbegin', svgFilter);
    }

    addEventListeners() {
        const navLinks = document.querySelectorAll('.gooey-nav .nav-link');
        const indicator = document.querySelector('.gooey-nav .nav-indicator');
        
        navLinks.forEach((link, index) => {
            link.addEventListener('mouseenter', () => {
                this.moveIndicator(link, indicator);
            });

            link.addEventListener('click', (e) => {
                // Убираем активный класс у всех ссылок
                navLinks.forEach(l => l.classList.remove('active'));
                // Добавляем активный класс к текущей ссылке
                link.classList.add('active');
                this.moveIndicator(link, indicator);
            });
        });

        // Возвращаем индикатор к активному элементу при выходе мыши
        document.querySelector('.gooey-nav').addEventListener('mouseleave', () => {
            const activeLink = document.querySelector('.gooey-nav .nav-link.active');
            if (activeLink) {
                this.moveIndicator(activeLink, indicator);
            }
        });
    }

    moveIndicator(targetLink, indicator) {
        const linkRect = targetLink.getBoundingClientRect();
        const navRect = targetLink.closest('.gooey-nav').getBoundingClientRect();
        
        const left = linkRect.left - navRect.left;
        const width = linkRect.width;
        
        indicator.style.transform = `translateX(${left}px)`;
        indicator.style.width = `${width}px`;
    }

    highlightCurrentPage() {
        const currentPath = window.location.pathname;
        const navLinks = document.querySelectorAll('.gooey-nav .nav-link');
        const indicator = document.querySelector('.gooey-nav .nav-indicator');
        
        navLinks.forEach(link => {
            const href = link.getAttribute('href');
            if (href === currentPath || 
                (currentPath === '/' && href === '/') ||
                (currentPath.includes('/admin') && href.includes('admin')) ||
                (currentPath.includes('/rating') && href.includes('rating'))) {
                link.classList.add('active');
                // Устанавливаем позицию индикатора для активной ссылки
                setTimeout(() => {
                    this.moveIndicator(link, indicator);
                }, 100);
            }
        });
    }
}

// Анимация появления навигации при скролле
function initScrollAnimation() {
    const navbar = document.querySelector('.gooey-navbar');
    let lastScrollY = window.scrollY;

    window.addEventListener('scroll', () => {
        if (window.scrollY > 100) {
            navbar.classList.add('scrolled');
        } else {
            navbar.classList.remove('scrolled');
        }

        // Скрываем/показываем навигацию при скролле
        if (window.scrollY > lastScrollY && window.scrollY > 200) {
            navbar.style.transform = 'translateY(-100%)';
        } else {
            navbar.style.transform = 'translateY(0)';
        }
        
        lastScrollY = window.scrollY;
    });
}

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', () => {
    new GooeyNav();
    initScrollAnimation();
});
