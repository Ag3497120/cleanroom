import CleanroomSite from './cleanroom-site';
import './cleanroom.css';
export default function Home(){return <CleanroomSite base={process.env.PAGES_BASE_PATH || ''}/>;}
